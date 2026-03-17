import sys
import threading
import uuid
import shutil
import logging
import queue
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from utils.paths import get_base_dir, get_resource_path

# 프로젝트 루트를 sys.path에 추가하여 agents 패키지 import 가능하게
BASE_DIR = get_base_dir()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from agents.frame_extractor import FrameExtractor
from agents.auto_labeler import AutoLabeler
from agents.grounding_dino_labeler import GroundingDINOLabeler
from agents.data_splitter import DataSplitter
from agents.dataset_organizer import DatasetOrganizer
from agents.roboflow_augmentor import RoboflowAugmentor

logger = logging.getLogger(__name__)


@dataclass
class PipelineState:
    run_id: str = ""
    status: str = "idle"  # idle, running, done, error
    current_step: int = 0
    total_steps: int = 5
    step_name: str = ""
    detail: str = ""
    error: Optional[str] = None
    download_ready: bool = False
    dataset_zip: Optional[str] = None
    events: queue.Queue = field(default_factory=queue.Queue)


class PipelineRunner:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.state = PipelineState()
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self.state.status == "running"

    def _emit(self, step: int, name: str, status: str, detail: str = "", **extra):
        self.state.current_step = step
        self.state.step_name = name
        self.state.detail = detail
        event = {
            "step": step,
            "total_steps": self.state.total_steps,
            "name": name,
            "status": status,
            "detail": detail,
            **extra,
        }
        self.state.events.put(event)

    def start(self, video_path: str, config: dict):
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Pipeline is already running")

        # 증강 활성화 시 7단계, 비활성화 시 5단계
        enable_aug = config.get("enable_augmentation", False)

        self.state = PipelineState()
        self.state.run_id = str(uuid.uuid4())[:8]
        self.state.status = "running"
        self.state.total_steps = 7 if enable_aug else 5

        thread = threading.Thread(
            target=self._run,
            args=(video_path, config),
            daemon=True,
        )
        thread.start()
        return self.state.run_id

    def _run(self, video_path: str, config: dict):
        run_dir = self.base_dir / "uploads" / self.state.run_id
        frames_dir = run_dir / "temp" / "frames"
        labels_dir = run_dir / "temp" / "labels"
        dataset_dir = run_dir / "dataset"
        enable_aug = config.get("enable_augmentation", False)
        total = self.state.total_steps

        try:
            # Step 1: 프레임 추출
            self._emit(1, "프레임 추출 중", "running")
            extractor = FrameExtractor(
                video_path=video_path,
                output_dir=str(frames_dir),
                frame_interval=config.get("frame_interval", 30),
                target_width=config.get("target_width"),
                target_height=config.get("target_height"),
            )
            result = extractor.run()
            image_paths = result["image_paths"]
            original_size = result["original_size"]
            resized_size = result["resized_size"]
            self._emit(1, "프레임 추출 완료", "done",
                       f"{len(image_paths)}장 추출 ({original_size[0]}x{original_size[1]})")

            # Step 2: 오토라벨링 (모드별 분기)
            labeling_mode = config.get("labeling_mode", "yolo")

            if labeling_mode == "grounding_dino":
                self._emit(2, "Grounding DINO 라벨링 중", "running",
                           "모델 로딩 중 (최초 실행 시 다운로드 소요)...")
                labeler = GroundingDINOLabeler(
                    class_names=config.get("class_names", ["object"]),
                    box_threshold=config.get("box_threshold", 0.35),
                    text_threshold=config.get("text_threshold", 0.25),
                    model_size=config.get("gdino_model_size", "base"),
                )
                label_dir = labeler.run(image_paths, str(labels_dir))
                self._emit(2, "Grounding DINO 라벨링 완료", "done",
                           f"{len(image_paths)}장 라벨 생성 (zero-shot)")
            else:
                self._emit(2, "YOLO 오토라벨링 중", "running")
                # 업로드된 모델 또는 기본 best.pt 사용
                model_id = config.get("model_id")
                if model_id:
                    model_matches = list(
                        (self.base_dir / "uploads").glob(f"model_{model_id}_*.pt")
                    )
                    model_path = str(model_matches[0]) if model_matches else str(
                        get_resource_path("best.pt")
                    )
                else:
                    model_path = str(get_resource_path("best.pt"))

                labeler = AutoLabeler(
                    model_path=model_path,
                    conf_threshold=config.get("conf_threshold", 0.5),
                )
                label_dir = labeler.run(image_paths, str(labels_dir))
                self._emit(2, "YOLO 오토라벨링 완료", "done",
                           f"{len(image_paths)}장 라벨 생성")

            # Step 3: 데이터 분할
            self._emit(3, "데이터 분할 중", "running")
            splitter = DataSplitter(
                train_ratio=config["train_ratio"] / 100,
                valid_ratio=config["valid_ratio"] / 100,
                test_ratio=config["test_ratio"] / 100,
            )
            split_data = splitter.run(image_paths, label_dir)
            counts = {k: len(v) for k, v in split_data.items()}
            self._emit(3, "데이터 분할 완료", "done",
                       f"train={counts['train']}, valid={counts['valid']}, test={counts['test']}")

            # Step 4: 데이터셋 구성
            self._emit(4, "데이터셋 구성 중", "running")
            if resized_size:
                imgsz = [resized_size[0], resized_size[1]]  # [width, height]
            elif original_size:
                imgsz = [original_size[0], original_size[1]]
            else:
                imgsz = None
            organizer = DatasetOrganizer(
                output_dir=str(dataset_dir),
                class_names=config.get("class_names", ["object"]),
                imgsz=imgsz,
            )
            organizer.run(split_data)
            self._emit(4, "데이터셋 구성 완료", "done", "data.yaml 생성 완료")

            if enable_aug:
                # Step 5: Roboflow 업로드 + 증강
                self._emit(5, "Roboflow 업로드 + 증강 중", "running")
                aug_config = config.get("augmentation", {})
                aug_settings = self._build_augmentation_settings(aug_config, imgsz)

                augmentor = RoboflowAugmentor(
                    api_key=config["roboflow_api_key"],
                    augmentation_settings=aug_settings,
                )
                augmented_dir = run_dir / "dataset_augmented"
                augmentor.run(str(dataset_dir), str(augmented_dir))
                self._emit(5, "Roboflow 증강 완료", "done", "증강 버전 생성 완료")

                # Step 6: 증강 데이터셋 다운로드 완료
                self._emit(6, "증강 데이터셋 정리 중", "running")
                # 증강된 데이터셋으로 ZIP 대상 교체
                final_dataset_dir = augmented_dir
                self._emit(6, "증강 데이터셋 정리 완료", "done", "증강된 데이터셋 준비 완료")

                # Step 7: ZIP 생성
                zip_step = 7
            else:
                final_dataset_dir = dataset_dir
                zip_step = 5

            # 최종: ZIP 생성
            self._emit(zip_step, "다운로드 파일 생성 중", "running")
            zip_path = shutil.make_archive(
                str(run_dir / "dataset"), "zip", str(final_dataset_dir))
            self.state.dataset_zip = zip_path
            self.state.download_ready = True
            self.state.status = "done"
            self._emit(zip_step, "완료", "done",
                       "데이터셋이 준비되었습니다", download_ready=True)

        except Exception as e:
            logger.exception("Pipeline error")
            self.state.status = "error"
            self.state.error = str(e)
            self._emit(self.state.current_step, self.state.step_name, "error",
                       str(e))
        finally:
            self._lock.release()

    @staticmethod
    def _build_augmentation_settings(aug_config: dict, imgsz: list[int] | None = None) -> dict:
        augmentation = {}

        if aug_config.get("flip_horizontal", False):
            augmentation["flip"] = {
                "horizontal": True,
                "vertical": aug_config.get("flip_vertical", False),
            }

        rotate = aug_config.get("rotate", 0)
        if rotate > 0:
            augmentation["rotate"] = {"degrees": rotate}

        blur = aug_config.get("blur", 0)
        if blur > 0:
            augmentation["blur"] = {"pixels": blur}

        brightness = aug_config.get("brightness", 0)
        if brightness > 0:
            augmentation["brightness"] = {
                "brighten": True,
                "darken": True,
                "percent": brightness,
            }

        versions = aug_config.get("versions", 3)
        augmentation["image"] = {"versions": max(1, min(versions, 50))}

        settings = {"augmentation": augmentation}

        if imgsz:
            w = imgsz[0] if isinstance(imgsz, list) else imgsz
            h = imgsz[1] if isinstance(imgsz, list) and len(imgsz) > 1 else w
            settings["preprocessing"] = {
                "auto-orient": True,
                "resize": {"width": w, "height": h, "format": "Stretch To"},
            }

        return settings

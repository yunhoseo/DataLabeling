import logging
import torch
from pathlib import Path
from PIL import Image
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

logger = logging.getLogger(__name__)

# 모델 ID 매핑
MODEL_REGISTRY = {
    "tiny": "IDEA-Research/grounding-dino-tiny",
    "base": "IDEA-Research/grounding-dino-base",
}


class GroundingDINOLabeler:
    """
    Grounding DINO 기반 zero-shot 오토 라벨러.

    커스텀 모델(best.pt) 없이 텍스트 프롬프트만으로 객체를 탐지하여
    YOLO txt 포맷 라벨을 생성한다.

    AutoLabeler와 동일한 인터페이스:
        run(image_paths, output_dir) -> str (label_dir 경로)
    """

    def __init__(
        self,
        class_names: list[str],
        box_threshold: float = 0.35,
        text_threshold: float = 0.25,
        model_size: str = "base",
    ):
        self.class_names = class_names
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold

        # 텍스트 프롬프트 생성: ["red_ball", "blue_car"] -> "red ball . blue car ."
        self.text_prompt = self._build_prompt(class_names)
        logger.info(f"  텍스트 프롬프트: '{self.text_prompt}'")

        # class_name -> class_id 매핑 (YOLO data.yaml 순서와 동일)
        self._label_to_id: dict[str, int] = {}
        for idx, name in enumerate(class_names):
            normalized = name.replace("_", " ").lower().strip()
            self._label_to_id[normalized] = idx

        # 디바이스 자동 감지
        self.device = self._select_device()

        # 모델 + 프로세서 로드 (HuggingFace 캐시 자동 관리)
        model_id = MODEL_REGISTRY.get(model_size, MODEL_REGISTRY["base"])
        logger.info(f"  Grounding DINO 모델 로딩: {model_id} (device={self.device})")
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(
            self.device
        )
        logger.info("  모델 로딩 완료")

    @staticmethod
    def _select_device() -> str:
        """CUDA > MPS(Apple Silicon) > CPU 순서로 디바이스 자동 감지"""
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
        logger.info(f"  추론 디바이스: {device}")
        return device

    @staticmethod
    def _build_prompt(class_names: list[str]) -> str:
        """
        클래스 이름 리스트를 Grounding DINO 텍스트 프롬프트 형식으로 변환.

        ["red_ball", "blue_car"] -> "red ball . blue car ."
        """
        parts = [name.replace("_", " ").strip() for name in class_names]
        return " . ".join(parts) + " ."

    def _match_label_to_class_id(self, label: str) -> int | None:
        """
        Grounding DINO가 반환한 라벨 텍스트를 class_id로 매핑.

        1. 정확 매칭 우선
        2. 부분 문자열 매칭 폴백 (DINO가 약간 다른 텍스트를 반환할 수 있음)
        """
        label_clean = label.lower().strip()

        # 정확 매칭
        if label_clean in self._label_to_id:
            return self._label_to_id[label_clean]

        # 부분 문자열 매칭
        for known_label, idx in self._label_to_id.items():
            if known_label in label_clean or label_clean in known_label:
                return idx

        return None

    def _convert_to_yolo(
        self, boxes, labels: list[str], img_width: int, img_height: int
    ) -> list[str]:
        """
        Grounding DINO 출력을 YOLO txt 포맷으로 변환.

        boxes: tensor (N, 4) - (x_min, y_min, x_max, y_max) 픽셀 좌표
        labels: 탐지된 라벨 텍스트 리스트
        Returns: ["0 0.500000 0.300000 0.200000 0.150000", ...] 형식의 문자열 리스트
        """
        lines = []
        for box, label in zip(boxes, labels):
            x_min, y_min, x_max, y_max = box.tolist()

            # YOLO 정규화 중심 좌표 변환
            cx = (x_min + x_max) / 2.0 / img_width
            cy = (y_min + y_max) / 2.0 / img_height
            w = (x_max - x_min) / img_width
            h = (y_max - y_min) / img_height

            # [0, 1] 범위로 클램핑
            cx = max(0.0, min(1.0, cx))
            cy = max(0.0, min(1.0, cy))
            w = max(0.0, min(1.0, w))
            h = max(0.0, min(1.0, h))

            # 라벨 텍스트 → class_id 매핑
            class_id = self._match_label_to_class_id(label)
            if class_id is None:
                logger.warning(f"  알 수 없는 라벨 '{label}' → 건너뜀")
                continue

            lines.append(f"{class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
        return lines

    def run(self, image_paths: list[str], output_dir: str) -> str:
        """
        Grounding DINO zero-shot 탐지 → YOLO txt 라벨 저장.

        AutoLabeler.run()과 동일한 인터페이스.

        Args:
            image_paths: 이미지 파일 경로 리스트
            output_dir: 라벨 출력 디렉토리
        Returns:
            label_dir 경로 (str)
        """
        output_dir = Path(output_dir).resolve()
        label_dir = output_dir / "labels"
        label_dir.mkdir(parents=True, exist_ok=True)

        detected_count = 0
        total = len(image_paths)

        for i, img_path in enumerate(image_paths):
            img = Image.open(img_path).convert("RGB")
            w, h = img.size

            # 프로세서로 입력 준비
            inputs = self.processor(
                images=img, text=self.text_prompt, return_tensors="pt"
            ).to(self.device)

            # 추론
            with torch.no_grad():
                outputs = self.model(**inputs)

            # 후처리: 바운딩 박스 + 라벨 추출
            results = self.processor.post_process_grounded_object_detection(
                outputs,
                inputs.input_ids,
                box_threshold=self.box_threshold,
                text_threshold=self.text_threshold,
                target_sizes=[(h, w)],
            )[0]

            boxes = results["boxes"]  # (N, 4) 픽셀 좌표
            labels = results["labels"]  # 라벨 텍스트 리스트

            # YOLO 포맷 변환
            lines = self._convert_to_yolo(boxes, labels, w, h)

            # 라벨 파일 저장 (탐지 없으면 빈 파일)
            stem = Path(img_path).stem
            lbl_path = label_dir / f"{stem}.txt"
            lbl_path.write_text("\n".join(lines) + ("\n" if lines else ""))

            if lines:
                detected_count += 1

            # 10장마다 진행 로그
            if (i + 1) % 10 == 0 or (i + 1) == total:
                logger.info(f"  진행: {i + 1}/{total}장 처리 완료")

        empty_count = total - detected_count
        logger.info(
            f"  → {total}개 라벨 생성 완료 (탐지: {detected_count}장, 빈 라벨: {empty_count}장)"
        )
        return str(label_dir)

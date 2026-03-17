import logging
import time
import shutil
from pathlib import Path

import roboflow

logger = logging.getLogger(__name__)


class RoboflowAugmentor:
    def __init__(self, api_key: str, project_name: str = "auto-label-augmentation",
                 augmentation_settings: dict | None = None):
        self.api_key = api_key
        self.project_name = project_name
        self.augmentation_settings = augmentation_settings or self._default_settings()

    @staticmethod
    def _default_settings() -> dict:
        return {
            "augmentation": {
                "flip": {"horizontal": True, "vertical": False},
                "rotate": {"degrees": 15},
                "blur": {"pixels": 1.0},
                "brightness": {"brighten": True, "darken": True, "percent": 15},
                "image": {"versions": 3},
            },
            "preprocessing": {
                "auto-orient": True,
                "resize": {"width": 640, "height": 640, "format": "Stretch To"},
            },
        }

    def run(self, dataset_dir: str, download_dir: str) -> str:
        """
        Roboflow에 데이터셋 업로드 → 증강 버전 생성 → 다운로드

        Args:
            dataset_dir: YOLO 형식 데이터셋 경로 (train/valid/test 포함)
            download_dir: 증강된 데이터셋 다운로드 경로

        Returns:
            다운로드된 데이터셋 경로
        """
        dataset_dir = Path(dataset_dir)
        download_dir = Path(download_dir)
        download_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: 인증
        logger.info("  Roboflow 인증 중...")
        rf = roboflow.Roboflow(api_key=self.api_key)
        workspace = rf.workspace()

        # Step 2: 프로젝트 생성
        project_id = self.project_name.lower().replace(" ", "-")
        timestamp = int(time.time())
        project_id = f"{project_id}-{timestamp}"

        logger.info(f"  프로젝트 생성: {project_id}")
        project = workspace.create_project(
            project_name=project_id,
            project_type="object-detection",
            project_license="MIT",
        )

        # Step 3: 데이터셋 업로드
        logger.info("  데이터셋 업로드 중...")
        workspace.upload_dataset(
            dataset_path=str(dataset_dir),
            project_id=project_id,
            num_workers=10,
            dataset_format="yolov8",
            project_type="object-detection",
            num_retries=3,
        )

        # Step 4: 증강 버전 생성
        logger.info("  증강 버전 생성 중...")
        project = workspace.project(project_id)
        version_info = project.generate_version(settings=self.augmentation_settings)
        logger.info(f"  증강 버전 생성 완료: {version_info}")

        # Step 5: 다운로드
        logger.info("  증강된 데이터셋 다운로드 중...")
        # generate_version은 버전 번호를 반환하거나 project.versions()에서 최신을 가져옴
        if isinstance(version_info, int):
            version_number = version_info
        else:
            versions = project.versions()
            version_number = len(versions)

        version = project.version(version_number)
        dataset = version.download("yolov8", location=str(download_dir), overwrite=True)

        download_path = str(download_dir)
        logger.info(f"  다운로드 완료: {download_path}")

        return download_path

import logging
from ultralytics import YOLO
from pathlib import Path

logger = logging.getLogger(__name__)


class AutoLabeler:
    def __init__(self, model_path: str, conf_threshold: float = 0.5):
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold

    def run(self, image_paths: list[str], output_dir: str) -> str:
        """
        이미지에 대해 추론 후 YOLO txt 라벨 저장
        Returns: 라벨이 저장된 디렉토리 경로

        source를 디렉토리로 전달하여 원본 파일명 유지
        """
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        # 이미지 디렉토리를 source로 전달 → 원본 파일명 유지
        frames_dir = Path(image_paths[0]).parent

        results = self.model.predict(
            source=str(frames_dir),
            conf=self.conf_threshold,
            save_txt=True,
            save=False,
            project=str(output_dir.parent),
            name=output_dir.name,
            exist_ok=True,
        )

        label_dir = output_dir / "labels"
        if not label_dir.exists():
            label_dir = output_dir

        n_labels = len(list(label_dir.glob("*.txt")))
        n_empty = len(image_paths) - n_labels
        if n_empty > 0:
            logger.info(f"  탐지 0건 이미지: {n_empty}장 (빈 라벨 생성)")
            for img_path in image_paths:
                stem = Path(img_path).stem
                lbl_path = label_dir / f"{stem}.txt"
                if not lbl_path.exists():
                    lbl_path.touch()

        logger.info(f"  → {len(list(label_dir.glob('*.txt')))}개 라벨 생성 완료")
        return str(label_dir)

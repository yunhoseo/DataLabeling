import shutil
import yaml
from pathlib import Path


class DatasetOrganizer:
    def __init__(self, output_dir: str, class_names: list[str],
                 imgsz: int | list[int] | None = None):
        self.output_dir = Path(output_dir)
        self.class_names = class_names
        self.imgsz = imgsz

    def run(self, split_data: dict) -> str:
        """폴더 구조 생성 + 파일 복사 + data.yaml 생성"""
        for split in ["train", "valid", "test"]:
            (self.output_dir / split / "images").mkdir(parents=True, exist_ok=True)
            (self.output_dir / split / "labels").mkdir(parents=True, exist_ok=True)

        for split, pairs in split_data.items():
            for img_path, lbl_path in pairs:
                shutil.copy2(img_path, self.output_dir / split / "images" / Path(img_path).name)
                shutil.copy2(lbl_path, self.output_dir / split / "labels" / Path(lbl_path).name)

        data_yaml = {
            "path": str(self.output_dir.resolve()),
            "train": "train/images",
            "val": "valid/images",
            "test": "test/images",
            "nc": len(self.class_names),
            "names": self.class_names,
        }
        if self.imgsz is not None:
            data_yaml["imgsz"] = self.imgsz

        yaml_path = self.output_dir / "data.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(data_yaml, f, default_flow_style=False, allow_unicode=True)

        return str(yaml_path)

"""
JSON 형식 → YOLO 라벨 형식 변환기.

지원 포맷:
  - COCO JSON  : 단일 파일 (images / annotations / categories 키 포함)
  - LabelMe JSON: 이미지별 단일 파일 (shapes / imageWidth / imageHeight 키 포함)
"""

import json
from pathlib import Path


class JsonToYoloConverter:
    """JSON 라벨 파일을 YOLO txt 포맷으로 변환."""

    # ------------------------------------------------------------------ #
    # 포맷 감지
    # ------------------------------------------------------------------ #

    @staticmethod
    def detect_format(data) -> str:
        """첫 번째 JSON 데이터 구조로 포맷을 자동 감지."""
        if isinstance(data, dict):
            if ("annotations" in data and "images" in data and "categories" in data):
                return "coco"
            if "shapes" in data and ("imageWidth" in data or "imageHeight" in data):
                return "labelme"
        elif isinstance(data, list) and data:
            if isinstance(data[0], dict) and "shapes" in data[0]:
                return "labelme"
        return "unknown"

    # ------------------------------------------------------------------ #
    # 진입점
    # ------------------------------------------------------------------ #

    def convert(self, json_files: list, output_dir: Path) -> dict:
        """
        파일 목록을 받아 자동 감지 후 변환.

        Returns:
            { format, class_names, image_count }
        """
        if not json_files:
            raise ValueError("변환할 JSON 파일이 없습니다.")

        first_data = json.loads(Path(json_files[0]).read_text(encoding="utf-8"))
        fmt = self.detect_format(first_data)

        if fmt == "coco":
            return self._convert_coco(first_data, output_dir)
        elif fmt == "labelme":
            all_data = []
            for jf in json_files:
                try:
                    d = json.loads(Path(jf).read_text(encoding="utf-8"))
                    if isinstance(d, list):
                        all_data.extend(d)
                    else:
                        all_data.append(d)
                except Exception:
                    pass
            return self._convert_labelme(all_data, output_dir)
        else:
            raise ValueError(
                "지원하지 않는 JSON 포맷입니다.\n"
                "• COCO 형식: images / annotations / categories 키 필요\n"
                "• LabelMe 형식: shapes / imageWidth / imageHeight 키 필요"
            )

    # ------------------------------------------------------------------ #
    # COCO 변환
    # ------------------------------------------------------------------ #

    def _convert_coco(self, data: dict, output_dir: Path) -> dict:
        categories = {c["id"]: c["name"] for c in data.get("categories", [])}
        cat_ids = sorted(categories.keys())
        cat_to_yolo = {cid: i for i, cid in enumerate(cat_ids)}
        class_names = [categories[cid] for cid in cat_ids]

        images = {img["id"]: img for img in data.get("images", [])}

        # 이미지별 annotation 그룹화
        ann_by_image: dict = {}
        for ann in data.get("annotations", []):
            ann_by_image.setdefault(ann["image_id"], []).append(ann)

        label_dir = output_dir / "labels"
        label_dir.mkdir(parents=True, exist_ok=True)

        count = 0
        for img_id, img_info in images.items():
            w = img_info.get("width", 1)
            h = img_info.get("height", 1)
            stem = Path(img_info["file_name"]).stem
            lines = []

            for ann in ann_by_image.get(img_id, []):
                if ann.get("iscrowd", 0):
                    continue
                x, y, bw, bh = ann["bbox"]           # COCO: top-left + w/h (절댓값)
                cx = (x + bw / 2) / w
                cy = (y + bh / 2) / h
                nw = bw / w
                nh = bh / h
                cid = cat_to_yolo[ann["category_id"]]
                lines.append(f"{cid} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

            (label_dir / f"{stem}.txt").write_text("\n".join(lines), encoding="utf-8")
            count += 1

        self._write_yaml(output_dir, class_names)
        return {"format": "COCO", "class_names": class_names, "image_count": count}

    # ------------------------------------------------------------------ #
    # LabelMe 변환
    # ------------------------------------------------------------------ #

    def _convert_labelme(self, all_data: list, output_dir: Path) -> dict:
        # 1패스: 전체 클래스 수집 (정렬로 일관성 유지)
        all_labels: set = set()
        for data in all_data:
            for shape in data.get("shapes", []):
                lbl = shape.get("label", "").strip()
                if lbl:
                    all_labels.add(lbl)

        class_names = sorted(all_labels)
        label_to_id = {lbl: i for i, lbl in enumerate(class_names)}

        label_dir = output_dir / "labels"
        label_dir.mkdir(parents=True, exist_ok=True)

        # 2패스: 변환
        count = 0
        for data in all_data:
            img_path = data.get("imagePath", "image.jpg")
            stem = Path(img_path).stem
            w = data.get("imageWidth") or 1
            h = data.get("imageHeight") or 1
            lines = []

            for shape in data.get("shapes", []):
                lbl = shape.get("label", "").strip()
                pts = shape.get("points", [])
                if not lbl or not pts or lbl not in label_to_id:
                    continue

                # rectangle / polygon / point 모두 bounding box로 변환
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                x1, y1 = min(xs), min(ys)
                x2, y2 = max(xs), max(ys)

                cx = ((x1 + x2) / 2) / w
                cy = ((y1 + y2) / 2) / h
                nw = (x2 - x1) / w
                nh = (y2 - y1) / h
                cid = label_to_id[lbl]
                lines.append(f"{cid} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

            (label_dir / f"{stem}.txt").write_text("\n".join(lines), encoding="utf-8")
            count += 1

        self._write_yaml(output_dir, class_names)
        return {"format": "LabelMe", "class_names": class_names, "image_count": count}

    # ------------------------------------------------------------------ #
    # 공통 유틸
    # ------------------------------------------------------------------ #

    @staticmethod
    def _write_yaml(output_dir: Path, class_names: list):
        """data.yaml 생성 (YOLO 학습 시 참조용)."""
        content = f"nc: {len(class_names)}\nnames: {class_names}\n"
        (output_dir / "data.yaml").write_text(content, encoding="utf-8")

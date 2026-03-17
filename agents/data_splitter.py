import random
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DataSplitter:
    def __init__(self, train_ratio=0.7, valid_ratio=0.2, test_ratio=0.1, seed=42):
        total = train_ratio + valid_ratio + test_ratio
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"split 비율 합계가 1.0이 아닙니다: {total:.4f}")
        if any(r < 0 for r in [train_ratio, valid_ratio, test_ratio]):
            raise ValueError("split 비율은 0 이상이어야 합니다.")

        self.train_ratio = train_ratio
        self.valid_ratio = valid_ratio
        self.test_ratio = test_ratio
        self.seed = seed

    def run(self, image_paths: list[str], label_dir: str) -> dict:
        """
        이미지-라벨 페어를 stem 기반으로 매칭하고 split
        Returns: {
            "train": [(img_path, lbl_path), ...],
            "valid": [(img_path, lbl_path), ...],
            "test":  [(img_path, lbl_path), ...],
        }
        """
        label_dir = Path(label_dir)

        label_map = {}
        for lbl_path in label_dir.glob("*.txt"):
            label_map[lbl_path.stem] = str(lbl_path)

        pairs = []
        missing_labels = []

        for img_path in image_paths:
            stem = Path(img_path).stem
            if stem in label_map:
                pairs.append((img_path, label_map[stem]))
            else:
                missing_labels.append(stem)
                logger.warning(f"  라벨 없음: {stem} (건너뜀)")

        if missing_labels:
            logger.warning(f"  라벨 미매칭 이미지: {len(missing_labels)}장")

        if len(pairs) == 0:
            raise RuntimeError("매칭된 이미지-라벨 페어가 0개입니다. 라벨 디렉토리를 확인하세요.")

        logger.info(f"  매칭된 페어: {len(pairs)}개")

        random.seed(self.seed)
        random.shuffle(pairs)

        n = len(pairs)
        n_train = int(n * self.train_ratio)
        n_valid = int(n * self.valid_ratio)

        result = {
            "train": pairs[:n_train],
            "valid": pairs[n_train:n_train + n_valid],
            "test":  pairs[n_train + n_valid:],
        }

        total_split = sum(len(v) for v in result.values())
        assert total_split == len(pairs), f"분할 후 데이터 누락: {total_split} != {len(pairs)}"

        return result

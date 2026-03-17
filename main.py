import yaml
import logging
from pathlib import Path
from agents.frame_extractor import FrameExtractor
from agents.auto_labeler import AutoLabeler
from agents.grounding_dino_labeler import GroundingDINOLabeler
from agents.data_splitter import DataSplitter
from agents.dataset_organizer import DatasetOrganizer

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def prompt_split_ratio() -> tuple[float, float, float]:
    """사용자에게 split 비율을 interactive하게 입력받기"""
    print("\n" + "=" * 50)
    print("  데이터 분할 비율 설정")
    print("=" * 50)
    print("  기본값: train=70%, valid=20%, test=10%")
    print("  Enter를 누르면 기본값이 적용됩니다.")
    print()

    try:
        train_input = input("  train 비율 (0~100, 기본=70): ").strip()
        train = float(train_input) / 100 if train_input else 0.7

        valid_input = input("  valid 비율 (0~100, 기본=20): ").strip()
        valid = float(valid_input) / 100 if valid_input else 0.2

        test = round(1.0 - train - valid, 4)

        if test < 0:
            logger.warning("train + valid > 100%. 기본값으로 되돌립니다.")
            return 0.7, 0.2, 0.1

        print(f"\n  → 적용 비율: train={train:.0%}, valid={valid:.0%}, test={test:.0%}")
        confirm = input("  이대로 진행할까요? (Y/n): ").strip().lower()
        if confirm in ("n", "no"):
            return prompt_split_ratio()

    except ValueError:
        logger.warning("잘못된 입력. 기본값으로 진행합니다.")
        return 0.7, 0.2, 0.1

    print("=" * 50 + "\n")
    return train, valid, test


def main(config_path: str = "config.yaml"):
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    temp_dir = Path(cfg.get("temp_dir", "./temp"))
    frames_dir = temp_dir / "frames"
    labels_dir = temp_dir / "labels"

    # Step 1: 프레임 추출 + 리사이즈
    logger.info("Step 1: Extracting frames...")
    extractor = FrameExtractor(
        video_path=cfg["video_path"],
        output_dir=str(frames_dir),
        frame_interval=cfg.get("frame_interval", 30),
        target_width=cfg.get("target_width", cfg.get("target_size")),
        target_height=cfg.get("target_height", cfg.get("target_size")),
    )
    extract_result = extractor.run()
    image_paths = extract_result["image_paths"]
    original_size = extract_result["original_size"]
    resized_size = extract_result["resized_size"]
    logger.info(f"  → {len(image_paths)} frames extracted")

    # Step 2: 오토라벨링 (모드별 분기)
    labeling_mode = cfg.get("labeling_mode", "yolo")

    if labeling_mode == "grounding_dino":
        logger.info("Step 2: Auto-labeling with Grounding DINO (zero-shot)...")
        labeler = GroundingDINOLabeler(
            class_names=cfg.get("class_names", ["object"]),
            box_threshold=cfg.get("box_threshold", 0.35),
            text_threshold=cfg.get("text_threshold", 0.25),
            model_size=cfg.get("gdino_model_size", "base"),
        )
    else:
        logger.info("Step 2: Auto-labeling with YOLO model...")
        labeler = AutoLabeler(
            model_path=cfg["model_path"],
            conf_threshold=cfg.get("conf_threshold", 0.5),
        )

    label_dir = labeler.run(image_paths, str(labels_dir))
    logger.info(f"  → 라벨 저장 위치: {label_dir}")

    # Step 3: Interactive split 비율 입력
    train_r, valid_r, test_r = prompt_split_ratio()

    # Step 4: 데이터 분할
    logger.info("Step 4: Splitting dataset...")
    splitter = DataSplitter(
        train_ratio=train_r,
        valid_ratio=valid_r,
        test_ratio=test_r,
    )
    split_data = splitter.run(image_paths, label_dir)
    for k, v in split_data.items():
        logger.info(f"  → {k}: {len(v)} pairs")

    # Step 5: 데이터셋 구성
    logger.info("Step 5: Organizing dataset...")
    if resized_size:
        imgsz = [resized_size[0], resized_size[1]]
    elif original_size:
        imgsz = [original_size[0], original_size[1]]
    else:
        imgsz = None
    organizer = DatasetOrganizer(
        output_dir=cfg.get("output_dir", "./dataset"),
        class_names=cfg.get("class_names", ["object"]),
        imgsz=imgsz,
    )
    yaml_path = organizer.run(split_data)
    logger.info(f"  → data.yaml: {yaml_path}")

    logger.info("=== Pipeline Complete ===")


if __name__ == "__main__":
    main()

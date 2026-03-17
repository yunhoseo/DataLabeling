import cv2
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FrameExtractor:
    def __init__(self, video_path: str, output_dir: str,
                 frame_interval: int = 30,
                 target_width: int | None = None,
                 target_height: int | None = None):
        self.video_path = video_path
        self.output_dir = Path(output_dir)
        self.frame_interval = frame_interval
        self.target_width = target_width
        self.target_height = target_height

    def run(self) -> dict:
        """
        프레임 추출 후 결과 반환
        Returns: {
            "image_paths": [...],
            "original_size": (w, h),
            "resized_size": (w, h) or None
        }
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cap = cv2.VideoCapture(self.video_path)
        saved_paths = []
        frame_count = 0
        original_size = None

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if original_size is None:
                h, w = frame.shape[:2]
                original_size = (w, h)
                logger.info(f"  원본 이미지 크기: {w}x{h}")

            if frame_count % self.frame_interval == 0:
                if self.target_width is not None and self.target_height is not None:
                    frame = cv2.resize(frame, (self.target_width, self.target_height),
                                       interpolation=cv2.INTER_LINEAR)

                filename = f"frame_{frame_count:06d}.png"
                save_path = str(self.output_dir / filename)
                cv2.imwrite(save_path, frame)
                saved_paths.append(save_path)

            frame_count += 1

        cap.release()

        resized_size = None
        if self.target_width is not None and self.target_height is not None:
            resized_size = (self.target_width, self.target_height)
            logger.info(f"  리사이즈: {original_size[0]}x{original_size[1]} → {self.target_width}x{self.target_height}")

        return {
            "image_paths": saved_paths,
            "original_size": original_size,
            "resized_size": resized_size,
        }

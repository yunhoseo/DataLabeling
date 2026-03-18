import os
import sys
import json
import uuid
import asyncio
import queue
import logging
from pathlib import Path

import yaml
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from pydantic import BaseModel, field_validator
from typing import Optional

from utils.paths import get_base_dir, get_resource_path

# 프로젝트 루트 설정
BASE_DIR = get_base_dir()
os.chdir(BASE_DIR)

from web.pipeline_runner import PipelineRunner

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

# config.yaml에서 Roboflow API Key 로드
_config_path = get_resource_path("config.yaml")
_cfg = yaml.safe_load(_config_path.read_text(encoding="utf-8")) if _config_path.exists() else {}
ROBOFLOW_API_KEY = _cfg.get("roboflow_api_key", "")

app = FastAPI(title="YOLO Auto-Label Pipeline")
runner = PipelineRunner(base_dir=BASE_DIR)

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}

# 변환 결과 임시 저장 (프로세스 재시작 전까지 유지)
_conv_results: dict = {}


class AugmentationConfig(BaseModel):
    flip_horizontal: bool = True
    flip_vertical: bool = False
    rotate: int = 15
    blur: float = 1.0
    brightness: int = 15
    versions: int = 3


class PipelineConfig(BaseModel):
    video_id: str
    frame_interval: int = 30
    target_width: int | None = 640
    target_height: int | None = 640
    conf_threshold: float = 0.5
    train_ratio: int = 70
    valid_ratio: int = 20
    test_ratio: int = 10
    class_names: list[str] = ["red_ball"]
    enable_augmentation: bool = False
    augmentation: Optional[AugmentationConfig] = None
    # --- 라벨링 모드 ---
    labeling_mode: str = "yolo"           # "yolo" | "grounding_dino"
    box_threshold: float = 0.35           # Grounding DINO box confidence
    text_threshold: float = 0.25          # Grounding DINO text-image matching
    gdino_model_size: str = "base"        # "tiny" | "base"
    model_id: Optional[str] = None        # 업로드된 YOLO 모델 참조 ID
    # --- Roboflow API Key (UI 입력) ---
    roboflow_api_key: Optional[str] = None

    @field_validator("labeling_mode")
    @classmethod
    def check_labeling_mode(cls, v):
        if v not in ("yolo", "grounding_dino"):
            raise ValueError("labeling_mode must be 'yolo' or 'grounding_dino'")
        return v

    @field_validator("conf_threshold")
    @classmethod
    def check_conf(cls, v):
        if not 0.01 <= v <= 1.0:
            raise ValueError("conf_threshold must be between 0.01 and 1.0")
        return v

    @field_validator("test_ratio")
    @classmethod
    def check_ratios_sum(cls, v, info):
        total = info.data.get("train_ratio", 0) + info.data.get("valid_ratio", 0) + v
        if total != 100:
            raise ValueError(f"Ratios must sum to 100, got {total}")
        return v


@app.get("/")
async def index():
    html_path = get_resource_path("web/templates/index.html")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.post("/api/upload")
async def upload_video(video: UploadFile = File(...)):
    ext = Path(video.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported format: {ext}")

    video_id = str(uuid.uuid4())[:8]
    filename = f"{video_id}_{video.filename}"
    save_path = UPLOAD_DIR / filename

    content = await video.read()
    save_path.write_bytes(content)
    size_mb = len(content) / (1024 * 1024)

    return {
        "video_id": video_id,
        "filename": video.filename,
        "size_mb": round(size_mb, 1),
        "saved_path": str(save_path),
    }


@app.post("/api/upload-model")
async def upload_model(model: UploadFile = File(...)):
    """커스텀 YOLO .pt 모델 파일 업로드"""
    ext = Path(model.filename).suffix.lower()
    if ext != ".pt":
        raise HTTPException(400, f"Only .pt files supported, got: {ext}")

    model_id = str(uuid.uuid4())[:8]
    filename = f"model_{model_id}_{model.filename}"
    save_path = UPLOAD_DIR / filename

    content = await model.read()
    save_path.write_bytes(content)
    size_mb = len(content) / (1024 * 1024)

    return {
        "model_id": model_id,
        "filename": model.filename,
        "size_mb": round(size_mb, 1),
        "saved_path": str(save_path),
    }


@app.get("/api/config-key-status")
async def config_key_status():
    """config.yaml에 Roboflow API Key가 설정되어 있는지 확인"""
    return {"has_key": bool(ROBOFLOW_API_KEY)}


@app.post("/api/run")
async def run_pipeline(config: PipelineConfig):
    if runner.is_running:
        raise HTTPException(409, "Pipeline is already running")

    # 업로드된 영상 찾기
    matches = list(UPLOAD_DIR.glob(f"{config.video_id}_*"))
    if not matches:
        raise HTTPException(404, "Uploaded video not found")
    video_path = str(matches[0])

    cfg = config.model_dump()

    # 증강 활성화 시 API Key 처리: UI 입력 > config.yaml > 에러
    if cfg.get("enable_augmentation"):
        ui_key = cfg.get("roboflow_api_key") or ""
        if ui_key.strip():
            cfg["roboflow_api_key"] = ui_key.strip()
        elif ROBOFLOW_API_KEY:
            cfg["roboflow_api_key"] = ROBOFLOW_API_KEY
        else:
            raise HTTPException(400, "Roboflow API Key가 필요합니다. UI에서 입력하거나 config.yaml에 설정하세요.")

    run_id = runner.start(video_path, cfg)
    return {"run_id": run_id, "status": "started"}


@app.get("/api/progress")
async def progress():
    async def event_generator():
        while True:
            try:
                event = runner.state.events.get_nowait()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("download_ready") or (event.get("status") == "error"):
                    break
            except queue.Empty:
                yield ": keepalive\n\n"
                await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/status")
async def status():
    return {
        "status": runner.state.status,
        "current_step": runner.state.current_step,
        "total_steps": runner.state.total_steps,
        "step_name": runner.state.step_name,
        "detail": runner.state.detail,
        "download_ready": runner.state.download_ready,
    }


@app.get("/api/download")
async def download():
    if not runner.state.download_ready or not runner.state.dataset_zip:
        raise HTTPException(404, "Dataset not ready for download")

    zip_path = Path(runner.state.dataset_zip)
    if not zip_path.exists():
        raise HTTPException(404, "ZIP file not found")

    return FileResponse(
        path=str(zip_path),
        filename=f"dataset_{runner.state.run_id}.zip",
        media_type="application/zip",
    )


# ============================================================
# JSON → YOLO 변환 API
# ============================================================

@app.post("/api/convert-json")
async def convert_json(files: list[UploadFile] = File(...)):
    """JSON 라벨 파일(COCO / LabelMe)을 YOLO txt 포맷으로 변환."""
    from agents.json_to_yolo_converter import JsonToYoloConverter
    import shutil

    if not files:
        raise HTTPException(400, "파일이 없습니다.")

    conv_id = str(uuid.uuid4())[:8]
    conv_dir = UPLOAD_DIR / f"conv_{conv_id}"
    json_in_dir = conv_dir / "json_input"
    yolo_out_dir = conv_dir / "yolo_output"
    json_in_dir.mkdir(parents=True, exist_ok=True)

    json_paths = []
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext != ".json":
            raise HTTPException(400, f"JSON 파일만 지원합니다: {f.filename}")
        content = await f.read()
        save_path = json_in_dir / f.filename
        save_path.write_bytes(content)
        json_paths.append(save_path)

    try:
        converter = JsonToYoloConverter()
        result = converter.convert(json_paths, yolo_out_dir)

        zip_path = shutil.make_archive(
            str(conv_dir / "yolo_labels"), "zip", str(yolo_out_dir)
        )

        _conv_results[conv_id] = {
            "zip_path": zip_path,
            "format": result["format"],
            "class_names": result["class_names"],
            "image_count": result["image_count"],
        }

        return {
            "convert_id": conv_id,
            "format": result["format"],
            "class_names": result["class_names"],
            "image_count": result["image_count"],
        }

    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        logging.exception("JSON 변환 오류")
        raise HTTPException(500, f"변환 중 오류가 발생했습니다: {e}")


@app.get("/api/convert-download/{convert_id}")
async def convert_download(convert_id: str):
    """변환된 YOLO 라벨 ZIP 다운로드."""
    info = _conv_results.get(convert_id)
    if not info:
        raise HTTPException(404, "변환 결과를 찾을 수 없습니다.")

    zip_path = Path(info["zip_path"])
    if not zip_path.exists():
        raise HTTPException(404, "ZIP 파일을 찾을 수 없습니다.")

    return FileResponse(
        path=str(zip_path),
        filename=f"yolo_labels_{convert_id}.zip",
        media_type="application/zip",
    )

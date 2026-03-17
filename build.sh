#!/bin/bash
set -euo pipefail

echo "=== YOLO Auto-Label Pipeline Build Script ==="
echo ""

# --- 설정 ---
CONDA_ENV="autolabel"
SPEC_FILE="datalabeling.spec"
DIST_DIR="dist"
BUILD_DIR="build"

# --- 프로젝트 루트로 이동 ---
cd "$(dirname "$0")"
echo "[1/6] 프로젝트 디렉토리: $(pwd)"

# --- conda 환경 활성화 ---
echo "[2/6] conda 환경 활성화: $CONDA_ENV"
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV"

# --- 환경 검증 ---
echo "[3/6] 환경 검증..."
python -c "
import sys
print(f'  Python: {sys.version}')
print(f'  Arch: {sys.platform}')
try:
    import torch; print(f'  torch: {torch.__version__}')
except: print('  torch: NOT FOUND')
try:
    import transformers; print(f'  transformers: {transformers.__version__}')
except: print('  transformers: NOT FOUND')
try:
    import ultralytics; print(f'  ultralytics: {ultralytics.__version__}')
except: print('  ultralytics: NOT FOUND')
try:
    import cv2; print(f'  cv2: {cv2.__version__}')
except: print('  cv2: NOT FOUND')
try:
    import fastapi; print(f'  fastapi: {fastapi.__version__}')
except: print('  fastapi: NOT FOUND')
try:
    import uvicorn; print(f'  uvicorn: {uvicorn.__version__}')
except: print('  uvicorn: NOT FOUND')
"

# --- PyInstaller 설치 ---
echo "[4/6] PyInstaller 설치 확인..."
pip install pyinstaller pyinstaller-hooks-contrib --quiet

# --- 이전 빌드 정리 ---
echo "[5/6] 이전 빌드 정리..."
rm -rf "$BUILD_DIR" "$DIST_DIR"

# --- PyInstaller 빌드 ---
echo "[6/6] PyInstaller 빌드 시작 (5-10분 소요)..."
echo ""
python -m PyInstaller "$SPEC_FILE" \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR" \
    --noconfirm \
    --log-level WARN

# --- 결과 확인 ---
echo ""
if [ -d "$DIST_DIR/DataLabeling" ]; then
    SIZE=$(du -sh "$DIST_DIR/DataLabeling" | cut -f1)
    echo "========================================"
    echo "  빌드 완료!"
    echo "========================================"
    echo "  출력 디렉토리: $DIST_DIR/DataLabeling/"
    echo "  실행 파일:     $DIST_DIR/DataLabeling/DataLabeling"
    echo "  전체 크기:     $SIZE"
    echo ""
    echo "  실행 방법:"
    echo "    ./$DIST_DIR/DataLabeling/DataLabeling"
    echo ""

    if [ -d "$DIST_DIR/DataLabeling.app" ]; then
        APP_SIZE=$(du -sh "$DIST_DIR/DataLabeling.app" | cut -f1)
        echo "  macOS 앱 번들: $DIST_DIR/DataLabeling.app ($APP_SIZE)"
        echo ""
    fi

    echo "  Gatekeeper 경고 해제 (필요 시):"
    echo "    xattr -cr $DIST_DIR/DataLabeling.app"
    echo "========================================"
else
    echo "ERROR: 빌드 출력을 찾을 수 없습니다!"
    exit 1
fi

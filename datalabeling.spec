# -*- mode: python ; coding: utf-8 -*-
"""
YOLO Auto-Label Pipeline - PyInstaller Build Spec (Cross-Platform)

빌드: python -m PyInstaller datalabeling.spec --noconfirm
출력: dist/DataLabeling/ (--onedir 모드)

지원 플랫폼:
  - macOS (arm64) → .app 번들
  - Windows (x64)  → .exe 실행파일
"""
import os
import sys
import webview.__pyinstaller as _wv_hook_pkg
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    collect_dynamic_libs,
)

# ============================================================
# 0. 플랫폼 감지
# ============================================================

IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

# pywebview 내장 PyInstaller 훅 디렉토리
webview_hook_path = os.path.dirname(_wv_hook_pkg.__file__)

block_cipher = None
project_root = os.path.abspath(".")

# ============================================================
# 1. 데이터 파일 수집
# ============================================================

# ultralytics: cfg/ 디렉토리의 YAML 설정 파일들 필수
ultralytics_datas = collect_data_files("ultralytics")

# transformers: 모델 레지스트리, tokenizer 설정 등
transformers_datas = collect_data_files("transformers", include_py_files=False)

# torch: 추가 데이터 파일
torch_datas = collect_data_files("torch")

# torch: 동적 라이브러리 (.dylib on macOS / .dll on Windows)
torch_libs = collect_dynamic_libs("torch")

# 프로젝트 리소스 파일
project_datas = [
    # HTML 템플릿
    (
        os.path.join(project_root, "web", "templates", "index.html"),
        os.path.join("web", "templates"),
    ),
    # 기본 설정
    (os.path.join(project_root, "config.yaml"), "."),
]

# YOLO 기본 모델 (있을 때만 포함)
_best_pt = os.path.join(project_root, "best.pt")
if os.path.exists(_best_pt):
    project_datas.append((_best_pt, "."))

# pywebview: JS 파일 (JS 인젝션용 필수)
webview_datas = collect_data_files("webview", subdir="js")

all_datas = project_datas + ultralytics_datas + transformers_datas + torch_datas + webview_datas

# ============================================================
# 2. Hidden Imports (플랫폼별 분기)
# ============================================================

hidden_imports = [
    # --- uvicorn 내부 모듈 (동적 import) ---
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # --- FastAPI / Starlette ---
    "starlette.responses",
    "starlette.routing",
    "starlette.middleware",
    "starlette.middleware.cors",
    # --- Pydantic V2 ---
    "pydantic",
    "pydantic_core",
    "pydantic.deprecated.decorator",
    "annotated_types",
    # --- PyTorch ---
    "torch",
    "torch._C",
    "torch.utils._pytree",
    # --- Transformers (Grounding DINO) ---
    "transformers",
    "transformers.models.grounding_dino",
    "transformers.models.grounding_dino.modeling_grounding_dino",
    "transformers.models.grounding_dino.processing_grounding_dino",
    "transformers.models.grounding_dino.configuration_grounding_dino",
    "transformers.models.grounding_dino.image_processing_grounding_dino",
    "transformers.image_processing_utils",
    "transformers.feature_extraction_utils",
    # --- OpenCV ---
    "cv2",
    # --- Ultralytics (YOLO) ---
    "ultralytics.nn",
    "ultralytics.nn.tasks",
    "ultralytics.engine",
    "ultralytics.utils",
    "ultralytics.cfg",
    # --- PIL (transformers/grounding dino 의존) ---
    "PIL",
    "PIL.Image",
    # --- Roboflow ---
    "roboflow",
    # --- multipart (파일 업로드) ---
    "multipart",
    "python_multipart",
    # --- YAML ---
    "yaml",
    # --- pywebview 공통 모듈 ---
    "webview",
    "webview.event",
    "webview.guilib",
    "webview.http",
    "webview.screen",
    "webview.util",
    "webview.window",
    "webview.dom",
    "webview.dom.dom",
    "webview.dom.element",
    "webview.dom.event",
    "webview.menu",
    "webview.localization",
    "webview.errors",
    # --- 표준 라이브러리 ---
    "encodings",
    "encodings.utf_8",
    "encodings.ascii",
]

# --- 플랫폼별 pywebview 백엔드 및 의존 모듈 ---
if IS_MACOS:
    hidden_imports += [
        # pywebview macOS 백엔드: Cocoa (WKWebView)
        "webview.platforms.cocoa",
        # pyobjc 프레임워크
        "objc",
        "AppKit",
        "Foundation",
        "WebKit",
        "Cocoa",
        "UniformTypeIdentifiers",
    ]
elif IS_WINDOWS:
    hidden_imports += [
        # pywebview Windows 백엔드: EdgeChromium / WinForms
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        # pythonnet (.NET 바인딩)
        "clr_loader",
        "pythonnet",
        "clr",
        # uvicorn / anyio Windows 백엔드
        # (누락 시 다른 PC에서 서버가 조용히 실패함)
        "anyio",
        "anyio._backends._asyncio",
        "anyio._backends._trio",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ]

# ultralytics와 roboflow의 모든 서브모듈 수집 (동적 import 많음)
hidden_imports += collect_submodules("ultralytics")
hidden_imports += collect_submodules("roboflow")

# ============================================================
# 3. Analysis
# ============================================================

a = Analysis(
    ["launcher.py"],
    pathex=[project_root],
    binaries=torch_libs,
    datas=all_datas,
    hiddenimports=hidden_imports,
    hookspath=[webview_hook_path],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 불필요한 대용량 패키지 제외 (번들 크기 절감)
        "matplotlib",
        "tkinter",
        "IPython",
        "jupyter",
        "jupyter_client",
        "jupyter_core",
        "notebook",
        # 주의: unittest는 제외하면 안 됨 (torch/utils/_config_module.py가 의존)
    ],
    noarchive=False,
    optimize=0,
)

# ============================================================
# 4. Build
# ============================================================

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# --- EXE 옵션: 플랫폼별 분기 ---
exe_kwargs = dict(
    exclude_binaries=True,  # --onedir 모드
    name="DataLabeling",
    debug=False,
    bootloader_ignore_signals=False,
    upx=False,  # torch 동적 라이브러리와 UPX 비호환
    console=False,  # GUI 앱: 콘솔 창 표시 안 함
)

if IS_MACOS:
    exe_kwargs["strip"] = False  # macOS arm64: strip하면 코드 서명 무효화
    exe_kwargs["target_arch"] = "arm64"
elif IS_WINDOWS:
    exe_kwargs["strip"] = False
    exe_kwargs["icon"] = os.path.join(project_root, "app.ico") if os.path.exists(os.path.join(project_root, "app.ico")) else None

exe = EXE(
    pyz,
    a.scripts,
    [],
    **exe_kwargs,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DataLabeling",
)

# ============================================================
# 5. macOS .app 번들 (macOS 전용)
# ============================================================

if IS_MACOS:
    app = BUNDLE(
        coll,
        name="DataLabeling.app",
        icon=None,  # .icns 아이콘 파일 경로 (없으면 기본 아이콘)
        bundle_identifier="com.autolabel.datalabeling",
        info_plist={
            "CFBundleName": "DataLabeling",
            "CFBundleDisplayName": "YOLO Auto-Label Pipeline",
            "CFBundleVersion": "1.0.0",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSBackgroundOnly": False,
            # macOS 네이티브 앱 설정
            "NSAppleEventsUsageDescription": "서버 시작 알림을 표시합니다.",
            "CFBundleDevelopmentRegion": "ko",
            "LSMinimumSystemVersion": "13.0",
            "NSSupportsAutomaticTermination": False,
            "NSSupportsSuddenTermination": False,
        },
    )

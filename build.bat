@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo === YOLO Auto-Label Pipeline Build Script (Windows) ===
echo.

:: --- 설정 ---
set CONDA_ENV=autolabel
set SPEC_FILE=datalabeling.spec
set DIST_DIR=dist
set BUILD_DIR=build

:: --- 프로젝트 루트로 이동 ---
cd /d "%~dp0"
echo [1/6] 프로젝트 디렉토리: %CD%

:: --- conda 환경 활성화 ---
echo [2/6] conda 환경 활성화: %CONDA_ENV%
call conda activate %CONDA_ENV%
if errorlevel 1 (
    echo ERROR: conda 환경 '%CONDA_ENV%' 활성화 실패
    echo   conda create -n %CONDA_ENV% python=3.10 으로 환경을 먼저 생성하세요.
    pause
    exit /b 1
)

:: --- 환경 검증 ---
echo [3/6] 환경 검증...
python -c "import sys; print(f'  Python: {sys.version}'); print(f'  Platform: {sys.platform}')"
python -c "try: import torch; print(f'  torch: {torch.__version__}')
except: print('  torch: NOT FOUND')"
python -c "try: import transformers; print(f'  transformers: {transformers.__version__}')
except: print('  transformers: NOT FOUND')"
python -c "try: import ultralytics; print(f'  ultralytics: {ultralytics.__version__}')
except: print('  ultralytics: NOT FOUND')"
python -c "try: import cv2; print(f'  cv2: {cv2.__version__}')
except: print('  cv2: NOT FOUND')"
python -c "try: import fastapi; print(f'  fastapi: {fastapi.__version__}')
except: print('  fastapi: NOT FOUND')"
python -c "try: import webview; print(f'  pywebview: {webview.__version__}')
except: print('  pywebview: NOT FOUND')"

:: --- PyInstaller 설치 확인 ---
echo [4/6] PyInstaller 설치 확인...
pip install pyinstaller pyinstaller-hooks-contrib --quiet

:: --- pythonnet 설치 확인 (Windows pywebview 의존) ---
pip install pythonnet --quiet

:: --- 이전 빌드 정리 ---
echo [5/6] 이전 빌드 정리...
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"

:: --- PyInstaller 빌드 ---
echo [6/6] PyInstaller 빌드 시작 (5-10분 소요)...
echo.
python -m PyInstaller "%SPEC_FILE%" --distpath "%DIST_DIR%" --workpath "%BUILD_DIR%" --noconfirm --log-level WARN

:: --- 결과 확인 ---
echo.
if not exist "%DIST_DIR%\DataLabeling\DataLabeling.exe" (
    echo ERROR: 빌드 출력을 찾을 수 없습니다!
    pause
    exit /b 1
)

echo ========================================
echo   PyInstaller 빌드 완료!
echo ========================================
echo   출력 디렉토리: %DIST_DIR%\DataLabeling\
echo   실행 파일:     %DIST_DIR%\DataLabeling\DataLabeling.exe
echo ========================================
echo.

:: ============================================================
:: [7/7] Inno Setup 인스톨러 빌드 (Inno Setup 설치된 경우)
::
:: 인스톨러를 만들면 Windows 사용자가 더블클릭 한 번으로
:: 설치 + MotW(Mark of the Web) 보안 해제까지 자동 처리됩니다.
::
:: Inno Setup 설치: https://jrsoftware.org/isdl.php
:: ============================================================
echo [7/7] Inno Setup 인스톨러 빌드...
set ISCC_PATH="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if exist %ISCC_PATH% (
    echo   Inno Setup 발견: %ISCC_PATH%
    if not exist "installer\Output" mkdir "installer\Output"

    %ISCC_PATH% "installer\windows_installer.iss"

    if errorlevel 1 (
        echo   WARNING: Inno Setup 빌드 실패. 계속합니다.
    ) else (
        echo.
        echo ========================================
        echo   인스톨러 빌드 완료!
        echo ========================================
        echo   인스톨러: installer\Output\DataLabeling-Setup-*.exe
        echo.
        echo   배포 방법:
        echo     installer\Output\DataLabeling-Setup-*.exe 를 배포하세요.
        echo     설치 후 Windows 보안 경고 없이 즉시 실행 가능합니다.
        echo ========================================
    )
) else (
    echo   Inno Setup이 설치되지 않았습니다. 인스톨러 빌드를 건너뜁니다.
    echo   설치 방법: https://jrsoftware.org/isdl.php
    echo   설치 후 이 스크립트를 다시 실행하면 인스톨러가 자동 생성됩니다.
)

echo.
pause

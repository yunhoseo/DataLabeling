"""
PyInstaller frozen 모드와 개발 모드 모두에서 동작하는 경로 해석 유틸리티.

- get_base_dir(): 프로젝트 루트 (쓰기 가능 작업 디렉토리)
- get_resource_path(): 번들된 읽기 전용 리소스 경로
"""
import sys
from pathlib import Path


def is_frozen() -> bool:
    """PyInstaller로 패키징된 상태인지 확인"""
    return getattr(sys, "frozen", False)


def get_base_dir() -> Path:
    """프로젝트 루트 디렉토리 반환.

    - frozen 모드: 실행 파일이 있는 디렉토리 (쓰기 가능)
    - 개발 모드: 이 파일의 상위 2단계 (utils/ → 프로젝트 루트)
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_resource_path(relative_path: str) -> Path:
    """번들된 리소스 파일의 절대 경로를 반환.

    PyInstaller --add-data로 번들된 파일은 sys._MEIPASS에 추출됨.
    개발 모드에서는 프로젝트 루트 기준 상대 경로.

    Args:
        relative_path: 프로젝트 루트 기준 상대 경로
                       (예: "web/templates/index.html", "config.yaml", "best.pt")
    """
    if is_frozen():
        # _MEIPASS에 번들된 리소스 확인
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled = Path(meipass) / relative_path
            if bundled.exists():
                return bundled
        # _MEIPASS에 없으면 실행 파일 옆에서 찾기
        return Path(sys.executable).resolve().parent / relative_path

    return Path(__file__).resolve().parent.parent / relative_path

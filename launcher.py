"""
YOLO Auto-Label Pipeline 실행 파일 진입점.

PyInstaller로 패키징된 상태와 개발 모드 모두에서 동작.
- 웹 서버(uvicorn) 백그라운드 시작
- pywebview 네이티브 창으로 UI 표시 (브라우저 불필요)
- 패키징 모드에서는 로그를 파일로 저장
- macOS / Windows 크로스 플랫폼 지원
"""
import multiprocessing
import os
import sys
import platform
import subprocess
import socket
import threading
import traceback
import logging
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def setup_logging(base_dir: Path):
    """macOS .app 모드에서는 콘솔이 없으므로 로그 파일로 출력."""
    log_dir = base_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "server.log"

    # stdout/stderr를 파일로 리다이렉트 (frozen 모드에서 콘솔 없을 때)
    if is_frozen():
        try:
            f = open(log_file, "w", encoding="utf-8")
            sys.stdout = f
            sys.stderr = f
        except Exception:
            pass  # 파일 열기 실패 시 무시

    return log_file


def find_free_port(default: int = 8000) -> int:
    """사용 가능한 포트 찾기. 기본 8000부터 순차 탐색."""
    for port in range(default, default + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return default


def wait_for_server(port: int, timeout: float = 60.0) -> bool:
    """서버가 준비될 때까지 폴링. 준비되면 True 반환."""
    import time
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


def show_notification(title: str, message: str):
    """크로스 플랫폼 네이티브 알림 표시. 실패 시 무시."""
    system = platform.system()
    try:
        if system == "Darwin":
            # macOS: osascript 알림
            os.system(
                f'osascript -e \'display notification "{message}" '
                f'with title "{title}"\''
            )
        elif system == "Windows":
            # Windows 10+: PowerShell 토스트 알림
            ps_script = (
                '[Windows.UI.Notifications.ToastNotificationManager, '
                'Windows.UI.Notifications, ContentType=WindowsRuntime] > $null; '
                '$xml = [Windows.UI.Notifications.ToastNotificationManager]'
                '::GetTemplateContent(0); '
                '$text = $xml.GetElementsByTagName("text"); '
                f'$text[0].AppendChild($xml.CreateTextNode("{title}")) > $null; '
                f'$text[1].AppendChild($xml.CreateTextNode("{message}")) > $null; '
                '$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); '
                '[Windows.UI.Notifications.ToastNotificationManager]'
                '::CreateToastNotifier("YOLO Pipeline").Show($toast)'
            )
            subprocess.Popen(
                ["powershell", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    except Exception:
        pass


# 로딩 중 표시할 HTML (서버가 준비되기 전)
LOADING_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>YOLO Auto-Label Pipeline</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #0f172a;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: #e2e8f0;
  }
  .logo {
    font-size: 2.5rem;
    font-weight: 700;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.5rem;
  }
  .subtitle {
    font-size: 1rem;
    color: #94a3b8;
    margin-bottom: 3rem;
  }
  .spinner {
    width: 48px;
    height: 48px;
    border: 4px solid #1e293b;
    border-top: 4px solid #6366f1;
    border-radius: 50%;
    animation: spin 0.9s linear infinite;
    margin-bottom: 1.5rem;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  .status {
    font-size: 0.9rem;
    color: #64748b;
  }
</style>
</head>
<body>
  <div class="logo">YOLO Auto-Label</div>
  <div class="subtitle">Pipeline</div>
  <div class="spinner"></div>
  <div class="status">앱을 시작하는 중입니다...</div>
</body>
</html>"""


def _error_html(error_msg: str, log_file: Path) -> str:
    """서버 시작 실패 시 pywebview 창에 표시할 에러 페이지."""
    safe_msg = str(error_msg).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_log = str(log_file).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>YOLO Auto-Label Pipeline — 오류</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #0f172a;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: #e2e8f0;
    padding: 2rem;
  }}
  .title {{ font-size: 1.5rem; font-weight: 700; color: #f87171; margin-bottom: 1rem; }}
  .subtitle {{ font-size: 0.95rem; color: #94a3b8; margin-bottom: 2rem; }}
  .card {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 1.5rem;
    max-width: 700px;
    width: 100%;
    margin-bottom: 1.5rem;
  }}
  .label {{ font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }}
  .code {{
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 0.8rem;
    color: #fca5a5;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 200px;
    overflow-y: auto;
  }}
  .log-path {{ color: #7dd3fc; font-family: monospace; font-size: 0.85rem; }}
  .hint {{ color: #64748b; font-size: 0.85rem; margin-top: 1rem; line-height: 1.6; }}
</style>
</head>
<body>
  <div class="title">앱 서버 시작 실패</div>
  <div class="subtitle">백엔드 서버가 시작되지 않았습니다.</div>
  <div class="card">
    <div class="label">오류 내용</div>
    <div class="code">{safe_msg}</div>
  </div>
  <div class="card">
    <div class="label">로그 파일 경로</div>
    <div class="log-path">{safe_log}</div>
    <div class="hint">위 경로의 로그 파일을 개발자에게 전달해주시면 문제를 해결하는 데 도움이 됩니다.</div>
  </div>
</body>
</html>"""


class NativeAPI:
    """pywebview JS API 브리지 — 네이티브 파일 저장 다이얼로그 처리."""

    def __init__(self, port: int):
        self._port = port

    def save_file_from_url(self, url: str, suggested_name: str) -> dict:
        """
        URL에서 파일을 다운로드하여 네이티브 저장 다이얼로그로 저장.

        Args:
            url: 절대 URL 또는 '/api/...' 형태의 상대 경로
            suggested_name: 기본 파일명 (예: 'dataset.zip')
        JS에서 window.pywebview.api.save_file_from_url(url, name) 로 호출.
        """
        import webview
        import urllib.request

        # 상대 경로 → 절대 URL 변환
        if url.startswith("/"):
            url = f"http://127.0.0.1:{self._port}{url}"

        try:
            window = webview.active_window()
            save_paths = window.create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=suggested_name,
                file_types=("ZIP Archive (*.zip)", "All Files (*.*)"),
            )
            if not save_paths:
                return {"success": False, "cancelled": True}

            save_path = save_paths if isinstance(save_paths, str) else save_paths[0]
            urllib.request.urlretrieve(url, save_path)
            return {"success": True, "path": save_path}

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}


def start_server(port: int, ready_event: threading.Event, server_error: list):
    """백그라운드 스레드에서 uvicorn 서버 시작."""
    try:
        from web.app import app
        print("  모듈 로딩 완료!", flush=True)
        ready_event.set()  # 모듈 로딩 완료 신호 (import 성공)

        import uvicorn
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",  # 네이티브 창 모드에서는 로그 최소화
        )
    except Exception as e:
        print(f"\n[ERROR] 서버 시작 실패: {e}", flush=True)
        traceback.print_exc()
        server_error[0] = f"{e}\n\n{traceback.format_exc()}"
        ready_event.set()  # 항상 main thread 해제 (무한 대기 방지)


def main():
    # PyInstaller frozen 환경 필수 설정
    multiprocessing.freeze_support()

    # torch 관련 환경 변수 (frozen 환경 안정성)
    os.environ.setdefault("PYTORCH_JIT", "0")
    os.environ.setdefault("OMP_NUM_THREADS", "1")

    from utils.paths import get_base_dir

    base_dir = get_base_dir()
    os.chdir(base_dir)

    # 로그 설정 (frozen 모드에서는 파일로 출력)
    log_file = setup_logging(base_dir)

    # 필요한 디렉토리 생성
    os.makedirs(str(base_dir / "uploads"), exist_ok=True)

    port = find_free_port(8000)

    print("=" * 50, flush=True)
    print("  YOLO Auto-Label Pipeline", flush=True)
    print("=" * 50, flush=True)
    print(f"  서버 주소: http://127.0.0.1:{port}", flush=True)
    print(f"  작업 디렉토리: {base_dir}", flush=True)
    print(f"  로그 파일: {log_file}", flush=True)
    print("=" * 50, flush=True)
    print(flush=True)

    try:
        import webview

        # macOS 알림: 로딩 시작
        if is_frozen():
            show_notification(
                "YOLO Auto-Label Pipeline",
                "앱을 시작하는 중입니다... (약 30초 소요)"
            )

        print("  모듈 로딩 중...", flush=True)

        # JS API 인스턴스 (파일 저장 다이얼로그 등)
        native_api = NativeAPI(port=port)

        # 네이티브 창 생성 (로딩 화면 표시)
        window = webview.create_window(
            title="YOLO Auto-Label Pipeline",
            html=LOADING_HTML,
            width=1280,
            height=820,
            min_size=(900, 600),
            resizable=True,
            js_api=native_api,
        )

        ready_event = threading.Event()

        def on_webview_started():
            """webview가 시작된 후 서버 초기화 및 URL 전환."""
            server_error = [None]  # 스레드 간 에러 공유 (리스트로 mutable 참조)

            # 서버를 별도 스레드에서 시작
            server_thread = threading.Thread(
                target=start_server,
                args=(port, ready_event, server_error),
                daemon=True,
            )
            server_thread.start()

            # 모듈 로딩 완료 대기 (최대 120초)
            ready_event.wait(timeout=120)

            # import 단계 실패 감지
            if server_error[0]:
                print(f"\n[ERROR] 서버 import 실패 — 에러 페이지 표시", flush=True)
                window.load_html(_error_html(server_error[0], log_file))
                return

            # 서버 포트 연결 대기 (최대 30초)
            if not wait_for_server(port, timeout=30):
                msg = "서버가 30초 내에 포트에 응답하지 않았습니다."
                print(f"\n[ERROR] {msg}", flush=True)
                window.load_html(_error_html(msg, log_file))
                return

            # 실제 앱 URL로 전환
            window.load_url(f"http://127.0.0.1:{port}")

            # 알림: 서버 시작 완료
            if is_frozen():
                show_notification(
                    "YOLO Auto-Label Pipeline",
                    "준비 완료!"
                )

        # webview 메인 루프 시작 (blocking)
        # on_webview_started는 webview GUI가 준비된 직후 별도 스레드에서 호출
        webview.start(on_webview_started, debug=False)

    except Exception as e:
        error_msg = f"앱 시작 실패: {e}"
        print(f"\n[ERROR] {error_msg}", flush=True)
        traceback.print_exc()

        if is_frozen():
            show_notification("YOLO Auto-Label Pipeline", error_msg)
            # 에러 내용을 별도 파일로 저장
            try:
                (base_dir / "logs" / "error.log").write_text(
                    f"{error_msg}\n\n{traceback.format_exc()}", encoding="utf-8"
                )
            except Exception:
                pass

        sys.exit(1)


if __name__ == "__main__":
    main()

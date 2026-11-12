import argparse
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser


def main():
    parser = argparse.ArgumentParser(description="数学竞赛备考工作台")
    parser.add_argument("--legacy-ui", action="store_true", help="启动旧版 Tkinter 界面")
    parser.add_argument("--no-browser", action="store_true", help="仅启动服务")
    args = parser.parse_args()
    base = Path(__file__).resolve().parent
    if args.legacy_ui:
        return subprocess.call([sys.executable, "-u", str(base / "launcher" / "app.py")], cwd=base)
    if not (base / "frontend" / "dist" / "index.html").is_file():
        print("前端尚未构建。请先运行：\n  npm --prefix frontend ci\n  npm --prefix frontend run build\n也可运行 python main.py --legacy-ui 使用旧版界面。")
        return 1
    try:
        import uvicorn
        from launcher.web_api import create_app
    except ImportError:
        print("缺少网页服务依赖，请运行 python -m pip install -r requirements.txt")
        return 1
    token = secrets.token_urlsafe(32)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    app = create_app(port, token)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False, timeout_graceful_shutdown=5))
    url = f"http://127.0.0.1:{port}/?session={token}"
    def ready():
        for _ in range(100):
            if server.started:
                print(f"工作台已启动：{url}\n关闭网页后任务继续运行；在此终端按 Ctrl+C 退出。", flush=True)
                if not args.no_browser:
                    webbrowser.open(url)
                return
            if server.should_exit:
                return
            time.sleep(.1)
    threading.Thread(target=ready, daemon=True).start()
    try:
        server.run(sockets=[sock])
    finally:
        app.state.manager.close()
        sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

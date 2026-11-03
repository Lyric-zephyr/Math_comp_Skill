import time
import sys
import subprocess
import os

def type_print(text, speed=0.01, color="\033[96m"):
    interactive = sys.stdout.isatty() and "debugpy" not in sys.modules
    if interactive:
        sys.stdout.write(color)
        for char in text:
            sys.stdout.write(char)
            sys.stdout.flush()
            time.sleep(min(speed, 0.001))
        print("\033[0m", flush=True)
    else:
        print(text, flush=True)

if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    type_print("[SYS] Mounting math-comp-prep SKILL modules...", speed=0.02)
    type_print("[SYS] Initializing Neural Network Adapters...", speed=0.02)
    type_print("[SYS] Booting Graphical User Interface...", speed=0.02, color="\033[92m")
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_PATH = os.path.join(BASE_DIR, "launcher", "app.py")
    
    try:
        result = subprocess.run([sys.executable, "-u", APP_PATH], cwd=BASE_DIR,
                                env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    except KeyboardInterrupt:
        print("\n[SYS] 程序已停止。", flush=True)
        sys.exit(130)
    except OSError as error:
        print(f"[ERR] 无法启动界面：{error}", file=sys.stderr, flush=True)
        sys.exit(1)
    if result.returncode:
        print(f"[ERR] 界面异常退出（退出码 {result.returncode}），请查看上方错误。", file=sys.stderr, flush=True)
    sys.exit(result.returncode)

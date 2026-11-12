import json
import os
import sys
from launcher.task_service import TaskService

if __name__ == "__main__":
    settings = json.loads(sys.stdin.readline())
    settings["api_key"] = os.environ.get("MATH_COMP_API_KEY", "")
    try:
        TaskService(lambda kind, data: print(data["text"], flush=True) if kind == "log" else None).setup_inline(settings)
    except Exception as error:
        print(f"[ERR] {error}", flush=True)
        sys.exit(1)

from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from launcher import web_api
from launcher.web_api import Manager, create_app

class Simulated:
    def __init__(self, emit):
        self.emit = emit
        self.stopping = False

    def execute(self, settings, kind):
        chapter = settings["chapter"]
        self.emit("module", {"chapter": chapter, "status": "running"})
        self.emit("progress", {"percent": 25, "stage": "正在生成测试内容"})
        for _ in range(20):
            if self.stopping:
                raise RuntimeError("服务退出")
            time.sleep(.1)
        if settings["model"] == "simulate-failure":
            raise RuntimeError("模拟服务错误 " + settings.get("api_key", ""))
        path = Path(web_api.BASE_DIR) / "output" / "学习内容.md"
        path.write_text("# 测试内容", encoding="utf-8")
        self.emit("artifact", {"path": str(path), "kind": "document", "chapter": chapter})
        self.emit("module", {"chapter": chapter, "status": "succeeded"})
        self.emit("progress", {"percent": 100, "stage": "全部完成"})
        return 1, 1

    def close(self):
        self.stopping = True

if __name__ == "__main__":
    dist = Path(__file__).resolve().parents[1] / "frontend/dist"
    with tempfile.TemporaryDirectory(prefix="math-comp-browser-test-") as temp:
        web_api.BASE_DIR = temp
        (Path(temp) / "output").mkdir()
        web_api.open_path = lambda path: None
        app = create_app(8124, "browser-test", Manager(Simulated), dist)
        uvicorn.run(app, host="127.0.0.1", port=8124, log_level="warning")

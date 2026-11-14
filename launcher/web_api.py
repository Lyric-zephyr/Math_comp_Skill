import asyncio
from collections import deque
from contextlib import asynccontextmanager
import copy
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from adapters.ai_runtime import API_SETTINGS, MODELS, RUN_MODES, api_model, list_api_models, validate_api_configuration
from adapters.skill_rules import MODULE_RULES, SUBJECT_MODULES, batch_chapters
from launcher.task_service import AI_PROVIDERS, BASE_DIR, SUBJECTS, TaskService

DEFAULTS = {"subject": SUBJECTS[0], "ai": "GPT (Codex)", "run_mode": "CLI", "model": MODELS["cli"][0], "mode": "总结知识点", "chapter": next(iter(MODULE_RULES)), "output_format": "pdf", "pdf_engine": "browser"}
TERMINAL = {"succeeded", "partial", "failed"}

class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = DEFAULTS["subject"]
    ai: str = DEFAULTS["ai"]
    run_mode: str = "CLI"
    model: str = Field(default=MODELS["cli"][0], max_length=300)
    mode: str = "总结知识点"
    chapter: str = DEFAULTS["chapter"]
    output_format: str = "pdf"
    pdf_engine: str = "browser"
    api_key: str | None = Field(default=None, max_length=4096, repr=False)

class Submission(BaseModel):
    kind: str = "generate"
    settings: Settings

class OpenArtifact(BaseModel):
    folder: bool = False

class Answer(BaseModel):
    keep: bool

class Manager:
    def __init__(self, service_factory=TaskService, event_limit=500):
        self.lock = threading.RLock()
        self.jobs = {}
        self.current = None
        self.artifacts = {}
        self.credentials = {}
        self.secrets = set()
        self.service_factory = service_factory
        self.event_limit = event_limit
        self.services = []
        self.threads = []
        self.closed = False

    def redact(self, value):
        if isinstance(value, str):
            with self.lock:
                secrets_snapshot = sorted(self.secrets, key=len, reverse=True)
            for secret in secrets_snapshot:
                if secret:
                    value = value.replace(secret, "[已隐藏]")
            return value
        if isinstance(value, dict):
            return {key: self.redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        return value

    def settings(self, raw, validate=False):
        data = raw.model_dump() if isinstance(raw, Settings) else dict(raw)
        ai = data["ai"]
        data.setdefault("subject", SUBJECTS[0])
        if data["subject"] not in SUBJECTS:
            raise HTTPException(422, "不支持的科目")
        if ai not in AI_PROVIDERS or data["run_mode"] not in RUN_MODES[AI_PROVIDERS[ai]]:
            raise HTTPException(422, "不支持的 AI 服务或运行方式")
        if data["mode"] not in ("总结知识点", "练习") or data["chapter"] not in (*SUBJECT_MODULES[data["subject"]], "all"):
            raise HTTPException(422, "无效任务或模块")
        if data["output_format"] not in ("word", "pdf", "md", "html") or data["pdf_engine"] not in ("browser", "latex"):
            raise HTTPException(422, "无效输出格式或引擎")
        provider = AI_PROVIDERS[ai]
        supplied = data.get("api_key")
        with self.lock:
            if supplied is not None:
                self.credentials[provider] = supplied.strip()
            key = self.credentials.get(provider, "") or os.environ.get(API_SETTINGS[provider][0], "")
            if key:
                self.secrets.add(key)
        data["api_key"] = key if data["run_mode"] == "API" else ""
        if validate and data["run_mode"] == "API":
            try:
                key, model, _ = validate_api_configuration(provider, key=key, model=data["model"])
                data.update(api_key=key, model=model)
            except ValueError as error:
                raise HTTPException(422, self.redact(str(error))) from None
        if validate and data["run_mode"] == "CLI" and not data["model"].strip():
            raise HTTPException(422, "请选择 CLI 模型")
        return data

    def snapshot(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            return self.redact({key: copy.deepcopy(value) for key, value in job.items() if key not in ("events", "service")})

    def emit(self, job_id, kind, data):
        with self.lock:
            job = self.jobs[job_id]
            if kind != "artifact":
                data = self.redact(data)
            if kind == "progress":
                job["percent"] = max(job["percent"], data["percent"])
                job["stage"] = data["stage"]
            elif kind == "log":
                job["logs"].append(data["text"])
                job["logs"] = job["logs"][-500:]
            elif kind == "module":
                job["modules"][data["chapter"]] = data["status"]
                job["successes"] = list(job["modules"].values()).count("succeeded")
                job["failures"] = list(job["modules"].values()).count("failed")
            elif kind == "ask":
                job["question"] = {"chapter": str(data.get("chapter", "")), "count": int(data.get("count", 0))}
                data = job["question"]
            elif kind == "artifact":
                path = Path(data["path"]).resolve()
                roots = [Path(BASE_DIR, "output").resolve(), Path(BASE_DIR, "local_problems").resolve()]
                if not path.is_file() or not any(path.is_relative_to(root) for root in roots):
                    return
                artifact_id = uuid.uuid4().hex
                self.artifacts[artifact_id] = path
                usage = data.get("usage")
                usage = {key: int(usage.get(key, 0)) for key in ("input", "output", "calls")} if isinstance(usage, dict) else None
                data = {"id": artifact_id, "name": path.name, "kind": data.get("kind", "document"), "chapter": data.get("chapter", ""), "usage": usage}
                data = self.redact(data)
                job["artifacts"].append(data)
            job["sequence"] += 1
            job["events"].append({"id": job["sequence"], "kind": kind, "data": data})

    def submit(self, kind, raw):
        if kind not in ("generate", "setup", "sources"):
            raise HTTPException(422, "无效操作")
        settings = self.settings(raw, validate=kind != "sources")
        if kind == "sources" and (settings["subject"] != "数学竞赛" or settings["mode"] != "练习"):
            raise HTTPException(422, "竞赛真题来源仅用于数学竞赛练习")
        with self.lock:
            if self.closed:
                raise HTTPException(503, "服务正在退出")
            if self.current and self.jobs[self.current]["status"] not in TERMINAL:
                raise HTTPException(409, "已有任务正在执行")
            job_id = uuid.uuid4().hex
            chapters = (batch_chapters(settings["subject"], settings["mode"]) if settings["chapter"] == "all" else [settings["chapter"]]) if kind == "generate" else []
            self.jobs[job_id] = {"id": job_id, "kind": kind, "status": "waiting", "percent": 0, "stage": "等待执行", "successes": 0, "failures": 0, "modules": {chapter: "waiting" for chapter in chapters}, "logs": [], "artifacts": [], "question": None, "sequence": 0, "events": deque(maxlen=self.event_limit)}
            self.current = job_id
            thread = threading.Thread(target=self.run, args=(job_id, kind, copy.deepcopy(settings)), daemon=True)
            self.threads.append(thread)
            thread.start()
            return self.snapshot(job_id)

    def run(self, job_id, kind, settings):
        service = self.service_factory(lambda event, data: self.emit(job_id, event, data))
        with self.lock:
            if self.closed:
                self.jobs[job_id].update(status="failed", stage="服务已退出", failures=1)
                return
            self.services.append(service)
            self.jobs[job_id]["status"] = "running"
        try:
            with self.lock:
                self.jobs[job_id]["service"] = service
            successes, total = service.execute(settings, kind)
            status = "succeeded" if successes == total else "partial" if successes else "failed"
            with self.lock:
                self.jobs[job_id].update(status=status, successes=successes, failures=total-successes)
        except Exception as error:
            self.emit(job_id, "log", {"text": "[ERR] " + str(error)})
            with self.lock:
                job = self.jobs[job_id]
                job.update(status="failed", failures=max(1, len(job["modules"])))
        finally:
            with self.lock:
                job = self.jobs[job_id]
                for chapter, state in job["modules"].items():
                    if state in ("waiting", "running"):
                        job["modules"][chapter] = "failed"
                job.pop("service", None)
                job["question"] = None
                job["stage"] = {"succeeded": "全部完成", "partial": "任务结束，存在失败项", "failed": "任务失败，请查看详细日志"}[job["status"]]
                self.services.remove(service)
            self.emit(job_id, "finished", {})

    def answer(self, job_id, keep):
        with self.lock:
            job = self.jobs[job_id]
            service = job.get("service")
            if not job["question"] or service is None:
                raise HTTPException(409, "当前没有待回答的问题")
            job["question"] = None
            job["sequence"] += 1
            job["events"].append({"id": job["sequence"], "kind": "ask", "data": None})
        if not service.answer(keep):
            raise HTTPException(409, "任务已结束，无法回答")
        return self.snapshot(job_id)

    def replay(self, job_id, cursor):
        with self.lock:
            job = self.jobs[job_id]
            events = list(job["events"])
            if cursor == 0 or cursor > job["sequence"] or (events and cursor < events[0]["id"] - 1):
                return [{"id": job["sequence"], "kind": "snapshot", "data": self.snapshot(job_id)}]
            return self.redact([event for event in events if event["id"] > cursor])

    def close(self):
        with self.lock:
            self.closed = True
            services = list(self.services)
        for service in services:
            service.close()
        for thread in self.threads:
            thread.join(timeout=3)


def open_path(path, reveal=False):
    path = Path(path).resolve(strict=True)
    if os.name == "nt" and (path.is_dir() or reveal):
        explorer = str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "explorer.exe")
        subprocess.Popen([explorer, *(["/select,"] if reveal and path.is_file() else []), str(path)])
    elif os.name == "nt":
        os.startfile(str(path))
    else:
        target = path.parent if reveal and path.is_file() else path
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(target)])
    return str(path.parent if reveal and path.is_file() else path)


def create_app(port, token=None, manager=None, dist=None):
    token = token or secrets.token_urlsafe(32)
    manager = manager or Manager()
    dist = Path(dist or Path(BASE_DIR) / "frontend" / "dist")
    origin = f"http://127.0.0.1:{port}"
    def matches(value):
        return hmac.compare_digest(value.encode("utf-8"), token.encode("utf-8"))

    @asynccontextmanager
    async def lifespan(app):
        yield
        manager.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.manager = manager

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({"detail": "请求格式无效，请检查输入"}, status_code=422)


    @app.middleware("http")
    async def guard(request, call_next):
        if request.headers.get("host") != f"127.0.0.1:{port}" or (request.headers.get("origin") not in (None, origin)):
            return JSONResponse({"detail": "来源不受信任"}, status_code=403)
        if request.url.path.startswith("/api/"):
            credential = request.headers.get("x-session-token", "") or request.cookies.get("math_session", "")
            if not matches(credential):
                return JSONResponse({"detail": "请从启动器打开工作台"}, status_code=401)
        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        if request.url.path.startswith("/api/") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index(request: Request):
        bootstrap = request.query_params.get("session", "")
        authorized = matches(bootstrap) or matches(request.cookies.get("math_session", ""))
        if not authorized:
            raise HTTPException(401, "请使用启动器打印的地址打开工作台")
        if not (dist / "index.html").is_file():
            return HTMLResponse("前端尚未构建。请运行 npm --prefix frontend ci 和 npm --prefix frontend run build", status_code=503)
        response = HTMLResponse((dist / "index.html").read_text(encoding="utf-8"))
        response.set_cookie("math_session", token, httponly=True, samesite="strict")
        return response

    @app.get("/api/options")
    def options():
        with manager.lock:
            configured = {ai: bool(manager.credentials.get(provider) or os.environ.get(API_SETTINGS[provider][0])) for ai, provider in AI_PROVIDERS.items()}
        return {"subjects": list(SUBJECTS), "providers": {ai: list(RUN_MODES[provider]) for ai, provider in AI_PROVIDERS.items()}, "modules": list(MODULE_RULES), "subject_modules": {subject: list(modules) for subject, modules in SUBJECT_MODULES.items()}, "batch_counts": {subject: {mode: len(batch_chapters(subject, mode)) for mode in ("总结知识点", "练习")} for subject in SUBJECTS}, "defaults": DEFAULTS, "api_defaults": {ai: (os.environ.get("OPENAI_MODEL", "") if provider == "codex" else api_model(provider)) for ai, provider in AI_PROVIDERS.items()}, "configured": configured, "cli_models": MODELS["cli"]}

    @app.put("/api/session/settings")
    def settings(raw: Settings):
        data = manager.settings(raw)
        configured = bool(data.pop("api_key"))
        return {**data, "configured": configured}

    @app.post("/api/models")
    def models(raw: Settings):
        data = manager.settings(raw)
        try:
            return {"models": list_api_models(AI_PROVIDERS[data["ai"]], data["api_key"])}
        except (OSError, ValueError, RuntimeError) as error:
            raise HTTPException(422, manager.redact(str(error))) from None

    @app.post("/api/jobs", status_code=202)
    def submit(raw: Submission):
        return manager.submit(raw.kind, raw.settings)

    @app.get("/api/jobs/current")
    def current():
        with manager.lock:
            return manager.snapshot(manager.current) if manager.current else None

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        if job_id not in manager.jobs:
            raise HTTPException(404, "任务不存在")
        return manager.snapshot(job_id)

    @app.post("/api/jobs/{job_id}/answer")
    def answer(job_id: str, raw: Answer):
        if job_id not in manager.jobs:
            raise HTTPException(404, "任务不存在")
        return manager.answer(job_id, raw.keep)

    @app.get("/api/jobs/{job_id}/events")
    async def events(job_id: str, request: Request):
        if job_id not in manager.jobs:
            raise HTTPException(404, "任务不存在")
        try:
            cursor = max(0, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            raise HTTPException(422, "无效事件序号") from None
        async def stream():
            nonlocal cursor
            heartbeat = time.monotonic()
            while not await request.is_disconnected():
                batch = manager.replay(job_id, cursor)
                for event in batch:
                    cursor = event["id"]
                    yield f"id: {cursor}\nevent: {event['kind']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
                if manager.snapshot(job_id)["status"] in TERMINAL:
                    return
                if time.monotonic() - heartbeat > 15:
                    yield ": heartbeat\n\n"
                    heartbeat = time.monotonic()
                await asyncio.sleep(.25)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @app.post("/api/resources/{name}/open")
    def resource(name: str):
        paths = {"textbook": Path(BASE_DIR) / "local_textbook", "output": Path(BASE_DIR) / "output"}
        if name not in paths:
            raise HTTPException(404, "目录不存在")
        try:
            paths[name].mkdir(exist_ok=True)
            opened = open_path(paths[name])
        except OSError:
            raise HTTPException(422, "无法打开文件夹，请检查系统文件管理器") from None
        return {"ok": True, "path": opened}

    @app.post("/api/artifacts/{artifact_id}/open")
    def artifact(artifact_id: str, action: OpenArtifact):
        with manager.lock:
            path = manager.artifacts.get(artifact_id)
        if not path or not path.is_file():
            raise HTTPException(404, "结果文件不存在或已被移动")
        resolved = path.resolve()
        if not any(resolved.is_relative_to(Path(BASE_DIR, directory).resolve()) for directory in ("output", "local_problems")):
            raise HTTPException(403, "结果文件路径已改变")
        try:
            opened = open_path(resolved, reveal=action.folder)
        except OSError:
            raise HTTPException(422, "文件已生成，但系统无法打开") from None
        return {"ok": True, "path": opened}

    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    return app

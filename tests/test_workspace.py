from pathlib import Path
import json
import os
import sys
import threading
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from launcher import task_service as tasks
from launcher import web_api as web
from launcher.web_api import DEFAULTS, Manager, Settings, create_app


class ControlledService:
    started = threading.Event()
    release = threading.Event()
    captured = None

    def __init__(self, emit):
        self.emit = emit

    def execute(self, settings, kind):
        type(self).captured = dict(settings)
        self.started.set()
        self.emit("progress", {"percent": 25, "stage": "生成中"})
        self.release.wait(5)
        self.emit("log", {"text": "provider error: " + settings.get("api_key", "")})
        return 1, 1

    def close(self):
        self.release.set()


def wait_done(manager, job_id):
    for _ in range(200):
        result = manager.snapshot(job_id)
        if result["status"] in web.TERMINAL:
            return result
        time.sleep(.01)
    pytest.fail("task did not finish")


@pytest.fixture
def client(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>工作台</html>", encoding="utf-8")
    ControlledService.started.clear()
    ControlledService.release.clear()
    manager = Manager(ControlledService, event_limit=3)
    app = create_app(8123, "test-token", manager, dist)
    with TestClient(app, base_url="http://127.0.0.1:8123") as client:
        assert client.get("/?session=test-token").status_code == 200
        yield client, manager
    ControlledService.release.set()


def test_origin_host_token_and_validation(client):
    client, manager = client
    assert client.get("/api/options", headers={"host": "evil.test:8123"}).status_code == 403
    assert client.post("/api/models", json=DEFAULTS, headers={"origin": "https://evil.test"}).status_code == 403
    client.cookies.clear()
    assert client.get("/api/options").status_code == 401
    assert client.get("/api/options", headers={"x-session-token": "test-token"}).status_code == 200
    assert client.get("/?session=wrong").status_code == 401
    assert client.get("/?session=错误令牌").status_code == 401
    client.get("/?session=test-token")
    invalid = client.put("/api/session/settings", json={**DEFAULTS, "api_key": "SECRET" * 1000})
    assert invalid.status_code == 422 and "SECRET" not in invalid.text


def test_subject_options_preserve_local_course_selector(client):
    client, manager = client
    options = client.get("/api/options").json()
    assert options["subjects"] == ["数学竞赛", "复变函数"]
    assert options["defaults"]["subject"] == "数学竞赛"
    raw = {**DEFAULTS, "subject": "复变函数"}
    assert client.put("/api/session/settings", json=raw).status_code == 200
    for kind in ("generate", "sources"):
        result = client.post("/api/jobs", json={"kind": kind, "settings": raw})
        assert result.status_code == 422 and "尚未接入" in result.json()["detail"]
    assert client.get("/api/jobs/current").json() is None
    assert client.put("/api/session/settings", json={**raw, "subject": "unknown"}).status_code == 422
    ControlledService.release.set()
    result = client.post("/api/jobs", json={"kind": "setup", "settings": raw})
    assert result.status_code == 202
    assert wait_done(manager, result.json()["id"])["status"] == "succeeded"


@pytest.mark.parametrize("kind", ["generate", "sources"])
def test_unimplemented_subject_never_runs_competition_backend(kind):
    service = tasks.TaskService(lambda *args: None)
    with pytest.raises(ValueError, match="尚未接入"):
        service.execute({**DEFAULTS, "subject": "复变函数"}, kind)


def test_launcher_cli_entry_point():
    import subprocess
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "main.py"), "--help"],
                            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr
    assert "Course_Skill" in result.stdout and "--legacy-ui" in result.stdout


def test_launcher_uses_project_environment(tmp_path, monkeypatch):
    import main as launcher
    local_python = tmp_path / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    local_python.parent.mkdir(parents=True)
    local_python.touch()
    monkeypatch.setattr(launcher, "__file__", str(tmp_path / "main.py"))
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "system-python"))
    monkeypatch.setattr(sys, "argv", ["main.py", "--no-browser"])
    with patch.object(launcher.subprocess, "call", return_value=0) as run:
        assert launcher.main() == 0
    run.assert_called_once_with([str(local_python), "-u", str(tmp_path / "main.py"), "--no-browser"], cwd=tmp_path)


def test_launcher_does_not_restart_inside_project_environment(tmp_path, monkeypatch):
    import main as launcher
    local_python = tmp_path / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    local_python.parent.mkdir(parents=True)
    local_python.touch()
    monkeypatch.setattr(launcher, "__file__", str(tmp_path / "main.py"))
    monkeypatch.setattr(sys, "prefix", str(tmp_path / ".venv"))
    monkeypatch.setattr(sys, "argv", ["main.py", "--legacy-ui"])
    with patch.object(launcher.subprocess, "call", return_value=0) as run:
        assert launcher.main() == 0
    run.assert_called_once_with([sys.executable, "-u", str(tmp_path / "launcher" / "app.py")], cwd=tmp_path)


def test_freeze_conflict_refresh_and_redaction(client):
    client, manager = client
    raw = {**DEFAULTS, "run_mode": "API", "model": "unit-model", "api_key": "unit-secret-key"}
    response = client.put("/api/session/settings", json=raw)
    assert response.status_code == 200 and "unit-secret-key" not in response.text
    job = client.post("/api/jobs", json={"kind": "generate", "settings": {**raw, "api_key": None}}).json()
    assert ControlledService.started.wait(2)
    assert client.post("/api/jobs", json={"kind": "setup", "settings": raw}).status_code == 409
    client.put("/api/session/settings", json={**raw, "model": "changed", "api_key": "replacement"})
    assert ControlledService.captured["model"] == "unit-model"
    assert ControlledService.captured["api_key"] == "unit-secret-key"
    assert client.get("/api/jobs/current").json()["id"] == job["id"]
    assert client.get("/").status_code == 200
    ControlledService.release.set()
    result = wait_done(manager, job["id"])
    assert result["status"] == "succeeded"
    assert "unit-secret-key" not in json.dumps(result)
    assert "[已隐藏]" in str(result["logs"])
    with client.stream("GET", f"/api/jobs/{job['id']}/events") as response:
        text = response.read().decode()
    assert "event: snapshot" in text and "unit-secret-key" not in text
    assert client.get("/api/jobs/missing").status_code == 404


def test_event_replay_overflow(client):
    client, manager = client
    job_id = client.post("/api/jobs", json={"settings": DEFAULTS}).json()["id"]
    ControlledService.started.wait(2)
    for i in range(8):
        manager.emit(job_id, "log", {"text": str(i)})
    replay = manager.replay(job_id, 1)
    assert replay[0]["kind"] == "snapshot"
    sequence = manager.snapshot(job_id)["sequence"]
    assert manager.replay(job_id, sequence) == []
    manager.emit(job_id, "log", {"text": "next"})
    assert manager.replay(job_id, sequence)[0]["data"]["text"] == "next"
    ControlledService.release.set()


def test_artifact_allowlist_and_fixed_resources(client, tmp_path, monkeypatch):
    client, manager = client
    monkeypatch.setattr(web, "BASE_DIR", str(tmp_path))
    output = tmp_path / "output"
    output.mkdir()
    good = output / "result.md"
    good.write_text("result")
    bad = tmp_path / "private.txt"
    bad.write_text("private")
    job_id = client.post("/api/jobs", json={"settings": DEFAULTS}).json()["id"]
    manager.emit(job_id, "artifact", {"path": str(bad)})
    assert manager.snapshot(job_id)["artifacts"] == []
    manager.emit(job_id, "artifact", {"path": str(good), "kind": "document"})
    artifact_id = manager.snapshot(job_id)["artifacts"][0]["id"]
    opened = []
    monkeypatch.setattr(web, "open_path", opened.append)
    assert client.post(f"/api/artifacts/{artifact_id}/open", json={}).status_code == 200
    assert opened == [good]
    assert client.post(f"/api/artifacts/{artifact_id}/open", json={"folder": True}).status_code == 200
    assert opened[-1] == output
    assert client.post("/api/artifacts/missing/open", json={}).status_code == 404
    assert client.post("/api/resources/private/open", json={}).status_code == 404
    good.unlink()
    assert client.post(f"/api/artifacts/{artifact_id}/open", json={}).status_code == 404
    ControlledService.release.set()


@pytest.fixture
def simulated(tmp_path, monkeypatch):
    (tmp_path / "output").mkdir()
    (tmp_path / "local_textbook").mkdir()
    script = tmp_path / "adapter.py"
    script.write_text('''import json, os, pathlib, sys
prefix = sys.argv[2]
fmt = sys.argv[sys.argv.index('--output-format') + 1]
print('[PROGRESS] 50 模拟生成', flush=True)
if '模块二' in prefix and os.environ.get('MATH_COMP_API_KEY') == 'fail-second':
    print('[-] simulated failure', flush=True)
    sys.exit(1)
path = pathlib.Path(prefix + ('.docx' if fmt == 'word' else '.' + fmt))
path.write_text(sys.argv[1], encoding='utf-8')
print('[ARTIFACT] ' + json.dumps({'path': str(path), 'kind': 'document'}), flush=True)
''', encoding="utf-8")
    monkeypatch.setattr(tasks, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(tasks, "AI_ADAPTERS", {ai: str(script) for ai in tasks.AI_PROVIDERS})
    monkeypatch.setattr(tasks, "check_output_environment", lambda *args: None)
    monkeypatch.setattr(tasks, "build_prompt", lambda mode, chapter, context, **kwargs: f"{mode}|{chapter}|{context}")
    return tmp_path


@pytest.mark.parametrize("ai,run_mode", [(ai, mode) for ai, provider in tasks.AI_PROVIDERS.items() for mode in web.RUN_MODES[provider]])
@pytest.mark.parametrize("output_format", ["pdf", "word", "md", "html"])
def test_real_subprocess_orchestration(simulated, ai, run_mode, output_format):
    events = []
    service = tasks.TaskService(lambda kind, data: events.append((kind, data)))
    settings = {**DEFAULTS, "ai": ai, "run_mode": run_mode, "model": "test", "output_format": output_format}
    assert service.execute(settings) == (1, 1)
    assert any(kind == "artifact" for kind, _ in events)
    progress = [data["percent"] for kind, data in events if kind == "progress"]
    assert progress == sorted(progress) and progress[-1] == 100


@pytest.mark.parametrize("mode,total", [("总结知识点", 6), ("练习", 7)])
def test_batch_partial_failure(simulated, mode, total):
    events = []
    service = tasks.TaskService(lambda kind, data: events.append((kind, data)))
    settings = {**DEFAULTS, "mode": mode, "chapter": "all", "run_mode": "API", "api_key": "fail-second", "output_format": "md"}
    assert service.execute(settings) == (total-1, total)
    assert len([1 for kind, data in events if kind == "module" and data["status"] == "succeeded"]) == total-1
    assert len([1 for kind, data in events if kind == "module" and data["status"] == "failed"]) == 1


def test_textbook_subprocess_and_reference_reuse(simulated):
    script = simulated / "skills/math-comp-prep/scripts/extract_pdf.py"
    script.parent.mkdir(parents=True)
    script.write_text("import pathlib,sys\npathlib.Path(sys.argv[sys.argv.index('--output')+1]).write_text('极限 连续 导数',encoding='utf-8')\nprint('[PROGRESS] 100 OCR完成')", encoding="utf-8")
    (simulated / "local_textbook/book.pdf").write_bytes(b"mock")
    service = tasks.TaskService(lambda *args: None)
    assert service.execute({**DEFAULTS, "output_format": "md"}) == (1, 1)
    content = next((simulated / "output").glob("*.md")).read_text(encoding="utf-8")
    assert "来源：book.pdf" in content and "极限 连续" in content


def test_setup_checks_export_and_ai(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks, "configure_environment", lambda *a, **k: calls.append("environment"))
    monkeypatch.setattr(tasks, "save_document", lambda *a, **k: calls.append("export"))
    monkeypatch.setattr(tasks, "configure_ai", lambda *a, **k: calls.append("ai"))
    tasks.TaskService(lambda *a: None).setup_inline(DEFAULTS)
    assert calls == ["environment", "export", "ai"]


@pytest.mark.parametrize("module", ["run_codex", "run_dsh", "run_doubao"])
def test_adapters_emit_actual_artifact(module, tmp_path, monkeypatch, capsys):
    import importlib
    adapter = importlib.import_module("adapters." + module)
    monkeypatch.setattr(adapter, "generate_content", lambda *a: "# 测试\n\n正文")
    monkeypatch.setattr(adapter, "open_document", lambda *a: None)
    result = adapter.main(["test", str(tmp_path / "result"), "--output-format", "md"])
    assert result == 0
    lines = capsys.readouterr().out.splitlines()
    artifact = json.loads(next(line.removeprefix("[ARTIFACT] ") for line in lines if line.startswith("[ARTIFACT] ")))
    assert Path(artifact["path"]).is_file()


def test_export_failure_preserves_registered_markdown(tmp_path, monkeypatch, capsys):
    from adapters import document_export
    monkeypatch.setattr(document_export, "check_output_environment", lambda *a: None)
    monkeypatch.setattr(document_export, "export_pdf", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("failed export")))
    with pytest.raises(RuntimeError):
        document_export.save_document("# recovery", tmp_path / "result", "pdf")
    line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("[ARTIFACT] "))
    data = json.loads(line.removeprefix("[ARTIFACT] "))
    assert data["kind"] == "recovery" and Path(data["path"]).read_text(encoding="utf-8").startswith("# recovery")


def test_worker_shutdown_stops_process_and_child(tmp_path):
    pytest.importorskip("psutil")
    import psutil
    child_file = tmp_path / "pid.txt"
    script = tmp_path / "parent.py"
    script.write_text("import subprocess,sys,time,pathlib\np=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\npathlib.Path(sys.argv[1]).write_text(str(p.pid))\ntime.sleep(60)")
    service = tasks.TaskService(lambda *a: None)
    parent = service.popen([sys.executable, str(script), str(child_file)])
    for _ in range(100):
        if child_file.exists():
            break
        time.sleep(.02)
    assert child_file.exists()
    child_pid = int(child_file.read_text())
    service.close()
    parent.wait(timeout=5)
    assert not psutil.pid_exists(child_pid) or psutil.Process(child_pid).status() == psutil.STATUS_ZOMBIE

def test_setup_worker_receives_secret_only_in_environment(simulated):
    worker = simulated / "launcher/setup_worker.py"
    worker.parent.mkdir()
    worker.write_text("import json,os,sys\ns=json.loads(sys.stdin.readline())\nassert 'api_key' not in s\nassert os.environ['MATH_COMP_API_KEY']=='worker-secret'\nprint('setup subprocess passed',flush=True)", encoding="utf-8")
    events = []
    service = tasks.TaskService(lambda kind, data: events.append((kind, data)))
    service.setup({**DEFAULTS, "api_key": "worker-secret"})
    assert any("setup subprocess passed" in data["text"] for kind, data in events if kind == "log")
    assert os.environ.get("MATH_COMP_API_KEY") != "worker-secret"


def test_credentials_reset_and_model_error_redaction(client, monkeypatch):
    client, manager = client
    raw = {**DEFAULTS, "run_mode": "API", "model": "unit-model", "api_key": "unit-secret-key"}
    client.put("/api/session/settings", json=raw)
    def fail(provider, key):
        raise RuntimeError("provider echoed " + key)
    monkeypatch.setattr(web, "list_api_models", fail)
    response = client.post("/api/models", json={**raw, "api_key": None})
    assert response.status_code == 422
    assert "unit-secret-key" not in response.text and "已隐藏" in response.text
    fresh = Manager()
    assert fresh.credentials == {} and fresh.current is None


def test_existing_textbook_cache_still_reused(tmp_path):
    import importlib.util
    fitz = pytest.importorskip("pymupdf")
    script = Path(__file__).resolve().parents[1] / "skills/math-comp-prep/scripts/extract_pdf.py"
    spec = importlib.util.spec_from_file_location("textbook_cache_check", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pdf = tmp_path / "textbook.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Calculus limits and continuity")
        document.save(pdf)
    logs = []
    cache = tmp_path / "cache"
    first = module.extract_text(pdf, log=logs.append, cache_dir=cache)
    logs.clear()
    second = module.extract_text(pdf, log=logs.append, cache_dir=cache)
    assert first == second and "Calculus" in second
    assert any("复用教材识别缓存" in line for line in logs)


@pytest.mark.parametrize("module", ["run_codex", "run_dsh", "run_doubao"])
def test_practice_structure_failure_emits_recovery(module, tmp_path, monkeypatch, capsys):
    import importlib
    adapter = importlib.import_module("adapters." + module)
    monkeypatch.setattr(adapter, "generate_content", lambda *a: "invalid practice")
    monkeypatch.setattr(adapter, "open_document", lambda *a: None)
    result = adapter.main(["任务：【练习】", str(tmp_path / "recovery"), "--output-format", "md"])
    assert result == 1
    line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("[ARTIFACT] "))
    data = json.loads(line.removeprefix("[ARTIFACT] "))
    assert data["kind"] == "recovery" and Path(data["path"]).is_file()

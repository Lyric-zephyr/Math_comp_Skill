import glob
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from adapters.document_export import check_output_environment, save_document
from adapters.setup_environment import configure_environment, configure_ai, refresh_path
from adapters.ai_runtime import API_SETTINGS
from adapters.skill_rules import ALL_MODULE_RULES, SUBJECT_MODULES, batch_chapters, build_prompt
from adapters.task_progress import parse_progress
from adapters.problem_sources import open_source_index

BASE_DIR = str(Path(__file__).resolve().parent.parent)
SUBJECTS = ("数学竞赛", "复变函数")
AI_PROVIDERS = {"GPT (Codex)": "codex", "DeepSeek (DSH)": "dsh", "豆包": "doubao"}
AI_ADAPTERS = {name: str(Path(BASE_DIR) / "adapters" / filename) for name, filename in zip(AI_PROVIDERS, ("run_codex.py", "run_dsh.py", "run_doubao.py"))}

class TaskService:
    def __init__(self, emit):
        self.emit = emit
        self.percent = 0
        self.processes = set()
        self.lock = threading.Lock()
        self.stopping = False
        self.secret = ""

    def log(self, text, prefix="[SYS]"):
        message = f"{prefix} {text}"
        if self.secret:
            message = message.replace(self.secret, "[已隐藏]")
        self.emit("log", {"text": message})

    def progress(self, percent, stage):
        if percent is not None:
            self.percent = max(self.percent, percent)
        self.emit("progress", {"percent": self.percent, "stage": stage})

    def popen(self, *args, **kwargs):
        with self.lock:
            if self.stopping:
                raise RuntimeError("服务正在退出")
            process = subprocess.Popen(*args, **kwargs)
            self.processes = {p for p in self.processes if p.poll() is None}
            self.processes.add(process)
            return process

    def close(self):
        import psutil
        with self.lock:
            self.stopping = True
            roots = [p for p in self.processes if p.poll() is None]
        for root in roots:
            try:
                parent = psutil.Process(root.pid)
                children = parent.children(recursive=True)
                protected = set()
                for child in children:
                    try:
                        command = " ".join(child.cmdline()).lower().replace("\\", "/")
                        if "--user-data-dir=" in command and "mathcompskill/browser" in command:
                            protected.add(child.pid)
                            protected.update(p.pid for p in child.children(recursive=True))
                    except psutil.Error:
                        pass
                workers = [child for child in reversed(children) if child.pid not in protected] + [parent]
                for worker in workers:
                    try:
                        worker.terminate()
                    except psutil.Error:
                        pass
                _, alive = psutil.wait_procs(workers, timeout=2)
                for worker in alive:
                    try:
                        worker.kill()
                    except psutil.Error:
                        pass
            except psutil.Error:
                pass

    def artifact_line(self, line, chapter):
        if not line.startswith("[ARTIFACT] "):
            return False
        try:
            data = json.loads(line[len("[ARTIFACT] "):])
            self.emit("artifact", {**data, "chapter": chapter})
        except (ValueError, TypeError):
            self.log("忽略无效产物消息", "[WARN]")
        return True

    def setup_inline(self, settings):
        failures = []
        try:
            configure_environment(settings["pdf_engine"], self.log, output_format=settings["output_format"])
            with tempfile.TemporaryDirectory(prefix="math-comp-env-") as work:
                save_document("# 输出格式检查\n\n中文正文与 **重点**。\n\n$$\\lim_{x\\to0}\\frac{\\sin x}{x}=1$$\n", Path(work) / "check", settings["output_format"], settings["pdf_engine"])
            self.log("输出环境与实际文件导出检查通过")
        except Exception as error:
            failures.append(str(error))
            self.log(str(error), "[ERR]")
        try:
            configure_ai(AI_PROVIDERS[settings["ai"]], settings["run_mode"], self.log, settings.get("api_key", ""), settings["model"])
        except Exception as error:
            failures.append(str(error))
            self.log(str(error), "[ERR]")
        if failures:
            raise RuntimeError("配置未完成，请查看错误日志")

    def setup(self, settings):
        self.secret = settings.get("api_key", "")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["MATH_COMP_API_KEY"] = settings.get("api_key", "")
        public = {key: value for key, value in settings.items() if key != "api_key"}
        with self.popen([sys.executable, "-u", "-m", "launcher.setup_worker"],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace", env=env, cwd=BASE_DIR) as process:
            process.stdin.write(json.dumps(public, ensure_ascii=False) + "\n")
            process.stdin.close()
            for line in process.stdout:
                self.log(line.rstrip(), "[FIX]")
            if process.wait():
                raise RuntimeError("配置未完成，请查看错误日志")

    def execute(self, settings, kind="generate"):
        subject = settings.get("subject", SUBJECTS[0])
        if subject not in SUBJECT_MODULES:
            raise ValueError("未知科目。")
        if kind == "sources" and (subject != "数学竞赛" or settings["mode"] != "练习"):
            raise ValueError("竞赛真题来源仅用于数学竞赛练习。")
        if kind == "generate" and settings["chapter"] not in (*SUBJECT_MODULES[subject], "all"):
            raise ValueError("模块与所选科目不匹配。")
        self.percent = 0
        if kind == "setup":
            self.setup(settings)
            self.progress(100, "环境配置完成")
            return 1, 1
        if kind == "sources":
            report = open_source_index(log=self.log)
            self.emit("artifact", {"path": str(report), "kind": "source", "chapter": "真题来源"})
            import webbrowser
            webbrowser.open(report.as_uri())
            self.progress(100, "来源索引完成")
            return 1, 1
        chapters = batch_chapters(subject, settings["mode"]) if settings["chapter"] == "all" else [settings["chapter"]]
        return self.run_all_tasks(settings["ai"], settings["mode"], chapters, settings["model"], settings["pdf_engine"], settings["run_mode"], settings.get("api_key", ""), settings["output_format"])

    def run_all_tasks(self, ai, mode, chapters, model_name, pdf_engine="browser", run_mode="CLI", api_key="", output_format="pdf"):
        total = len(chapters)
        successes = 0
        processed = 0
        self.secret = api_key or os.environ.get(API_SETTINGS[AI_PROVIDERS[ai]][0], "")
        try:
            refresh_path()
            self.progress(2, "检查运行环境")
            check_output_environment(output_format, pdf_engine)
            self.progress(5, "准备读取教材")
            output_dir = os.path.join(BASE_DIR, "output")
            os.makedirs(output_dir, exist_ok=True)
            textbook_files = sorted(glob.glob(os.path.join(BASE_DIR, "local_textbook", "*.pdf")))
            extract_script = os.path.join(BASE_DIR, "skills", "Common", "scripts", "extract_pdf.py")
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            # 提取脚本校验文件内容及识别流程，命中缓存时直接复用；本批模块共享正文。
            textbook_texts = {}
            for book_index, pdf_path in enumerate(textbook_files):
                self.log(f"正在提取教材: {os.path.basename(pdf_path)}", "[TEXTBOOK]")
                try:
                    # 正文写入临时文件，日志实时显示；OCR 按批超时，整本书不再限时 120 秒。
                    with tempfile.TemporaryDirectory(prefix="math-comp-textbook-") as directory:
                        text_path = Path(directory) / "textbook.txt"
                        with self.popen(
                            [sys.executable, "-u", extract_script, pdf_path, "--output", str(text_path)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", env=env,
                        ) as process:
                            for line in process.stdout:
                                progress = parse_progress(line)
                                if progress:
                                    value, stage = progress
                                    self.progress(5 + 20 * (book_index + value / 100) / len(textbook_files),
                                            f"教材 {book_index + 1}/{len(textbook_files)} · {stage}")
                                elif line.strip():
                                    self.log(line.strip(), "[TEXTBOOK]")
                            return_code = process.wait()
                        if return_code:
                            self.log(f"教材提取失败: {os.path.basename(pdf_path)}（退出码 {return_code}）；请查看上方错误。", "[ERR]")
                            continue
                        text = text_path.read_text(encoding="utf-8")
                    if text.strip():
                        textbook_texts[pdf_path] = text
                    else:
                        self.log(f"{os.path.basename(pdf_path)} 提取和 OCR 后仍没有可用文字。", "[WARN]")
                except (OSError, subprocess.TimeoutExpired) as error:
                    self.log(f"教材提取失败: {os.path.basename(pdf_path)}: {error}", "[ERR]")
                finally:
                    self.progress(5 + 20 * (book_index + 1) / len(textbook_files), "教材读取阶段完成")
            self.progress(25, "准备生成正文")
            if not textbook_texts:
                self.log("没有可用的用户教材文本，将在线读取 GitHub Assistant_course 对应资料；不足部分由 AI 知识补齐。", "[WARN]")

            for i, chap in enumerate(chapters):
                if self.stopping:
                    break
                self.emit("module", {"chapter": chap, "status": "running"})
                task_start, task_share = 25 + 75 * i / total, 75 / total
                self.progress(task_start, f"模块 {i + 1}/{total} · 整理参考资料")
                self.log(f"队列进度 [{i+1}/{total}] 开始处理: {chap}", "[QUEUE]")
                try:
                    keywords = ALL_MODULE_RULES[chap][1]
                    references = []
                    budget = 20000 // max(len(textbook_texts), 1)
                    for pdf_path, text in textbook_texts.items():
                        excerpts = []
                        remaining = budget
                        for offset in range(0, len(text), 1000):
                            chunk = text[offset:offset + 1200]
                            if any(keyword in chunk for keyword in keywords):
                                excerpts.append(chunk[:remaining])
                                remaining -= len(excerpts[-1])
                                if remaining <= 0:
                                    break
                        if excerpts:
                            references.append(f"--- 来源：{os.path.basename(pdf_path)} ---\n" + "\n".join(excerpts))
                    prompt_context = "\n\n".join(references)[:20000]
                    if textbook_texts and not prompt_context:
                        self.log(f"未找到与 {chap} 匹配的教材片段。", "[WARN]")
                    prompt = build_prompt(mode, chap, prompt_context, log=lambda message: self.log(message, "[SOURCE]" if mode == "练习" else "[RULE]"))
                    safe_name = f"{mode}_{chap}".replace("：", "_").replace(" ", "")
                    cmd = [sys.executable, "-u", AI_ADAPTERS[ai], "", os.path.join(output_dir, safe_name)]
                    if ai == "GPT (Codex)" and run_mode == "CLI":
                        cmd.append(model_name)
                    cmd.extend(["--pdf-engine", pdf_engine, "--run-mode", run_mode, "--output-format", output_format])
                    adapter_env = env.copy()
                    if run_mode == "API":
                        cmd.extend(["--api-model", model_name])
                        if api_key:
                            adapter_env["MATH_COMP_API_KEY"] = api_key
                    with tempfile.TemporaryDirectory(prefix="course-skill-prompt-") as request_dir:
                        prompt_file = Path(request_dir) / "prompt.txt"
                        prompt_file.write_text(prompt, encoding="utf-8")
                        cmd.extend(["--prompt-file", str(prompt_file)])
                        with self.popen(
                            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", env=adapter_env, cwd=BASE_DIR,
                        ) as process:
                            for line in process.stdout:
                                progress = parse_progress(line)
                                if progress:
                                    value, stage = progress
                                    self.progress(task_start + task_share * value / 100,
                                            f"模块 {i + 1}/{total} · {stage}")
                                elif not self.artifact_line(line, chap):
                                    self.log(line.rstrip())
                            return_code = process.wait()
                    self.emit("module", {"chapter": chap, "status": "failed" if return_code else "succeeded"})
                    if return_code:
                        self.log(f"失败: {chap}（退出码 {return_code}）", "[ERR]")
                    else:
                        successes += 1
                        self.log(f"完成: {chap}", "[DONE]")
                except Exception as error:
                    self.emit("module", {"chapter": chap, "status": "failed"})
                    self.log(f"执行失败: {chap}: {error}", "[ERR]")
                finally:
                    processed = i + 1
                    self.progress(task_start + task_share, f"已处理 {processed}/{total} 个模块")
        except Exception as error:
            self.log(f"队列执行失败: {error}", "[ERR]")
        finally:
            status = "全部完成" if total and successes == total else "任务结束，存在失败项"
            self.progress(100 if total and processed == total else None, status)
            self.log(f"队列结束：成功 {successes} 项，失败 {total - successes} 项。成功文件保存在 output 文件夹。")
            return successes, total

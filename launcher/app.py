import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess
import threading
import os
import time
import glob
import queue
import sys
import tempfile
import webbrowser
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from adapters.document_export import OUTPUT_FORMATS, check_output_environment, save_document
from adapters.setup_environment import configure_environment, configure_ai
from adapters.ai_runtime import API_SETTINGS, RUN_MODES, api_model, list_api_models, validate_api_configuration
from adapters.skill_rules import MODULE_RULES, build_prompt
from adapters.problem_sources import open_source_index
from adapters.task_progress import parse_progress

AI_ADAPTERS = {
    "GPT (Codex)": os.path.join(BASE_DIR, "adapters", "run_codex.py"),
    "DeepSeek (DSH)": os.path.join(BASE_DIR, "adapters", "run_dsh.py"),
    "豆包": os.path.join(BASE_DIR, "adapters", "run_doubao.py")
}

AI_PROVIDERS = {"GPT (Codex)": "codex", "DeepSeek (DSH)": "dsh", "豆包": "doubao"}
AI_RUN_MODES = {name: RUN_MODES[provider] for name, provider in AI_PROVIDERS.items()}

PDF_ENGINES = {"浏览器（推荐）": "browser", "LaTeX（专业排版）": "latex"}


class MathApp:
    def __init__(self, root):
        self.root = root
        self.ui_events = queue.Queue()
        self.root.title("MATH COMP // Competition workspace")
        self.root.configure(bg="#0a0a0f")
        self.root.minsize(1100, 800)
        width = min(1280, self.root.winfo_screenwidth() - 60)
        height = min(920, self.root.winfo_screenheight() - 90)
        self.root.geometry(f"{width}x{height}")

        panel = "#11151f"
        muted = "#8494aa"
        accent = "#00ffcc"
        text = "#e1e9f3"
        font = ("Microsoft YaHei UI", 12)
        mono = ("Consolas", 12)
        self.root.option_add("*TCombobox*Listbox.font", font)
        self.root.option_add("*TCombobox*Listbox.background", "#171f2b")
        self.root.option_add("*TCombobox*Listbox.foreground", text)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#164a47")
        self.root.option_add("*TCombobox*Listbox.selectForeground", accent)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Cyber.TCombobox", fieldbackground="#0c111b", background="#1c2838",
                        foreground=text, arrowcolor=accent, bordercolor="#28364a",
                        lightcolor="#28364a", darkcolor="#28364a", padding=4)
        style.map("Cyber.TCombobox", fieldbackground=[("readonly", "#0c111b"), ("disabled", "#121822")],
                  foreground=[("disabled", "#536076"), ("readonly", text)],
                  selectbackground=[("readonly", "#0c111b")], selectforeground=[("readonly", text)],
                  bordercolor=[("focus", accent)])
        style.configure("Cyber.TEntry", fieldbackground="#0c111b", foreground=text,
                        insertcolor=accent, bordercolor="#28364a", lightcolor="#28364a",
                        darkcolor="#28364a", padding=6)
        style.map("Cyber.TEntry", bordercolor=[("focus", accent)])
        style.configure("Cyber.Horizontal.TProgressbar", troughcolor="#1b2534", background=accent,
                        bordercolor="#1b2534", lightcolor=accent, darkcolor=accent, thickness=7)
        style.configure("Cyber.Vertical.TScrollbar", background="#253449", troughcolor="#090d14",
                        arrowcolor=muted, bordercolor="#090d14")

        self.main_frame = tk.Frame(root, bg="#0a0a0f")
        self.main_frame.pack(fill="both", expand=True, padx=22, pady=16)
        self.main_frame.columnconfigure(0, weight=6, minsize=560)
        self.main_frame.columnconfigure(1, weight=5, minsize=440)
        self.main_frame.rowconfigure(2, weight=1)

        header = tk.Frame(self.main_frame, bg="#0a0a0f")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        tk.Label(header, text="MATH COMP", font=("Consolas", 26, "bold"),
                 bg="#0a0a0f", fg=accent).pack(anchor="w")
        tk.Label(header, text="数学竞赛备考工作台   /   HIGHER MATHEMATICS WORKSPACE",
                 font=("Microsoft YaHei UI", 11), bg="#0a0a0f", fg=muted).pack(anchor="w", pady=(1, 0))
        tk.Frame(self.main_frame, bg="#243448", height=1).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        settings = tk.Frame(self.main_frame, bg="#0a0a0f")
        settings.grid(row=2, column=0, sticky="nsew", padx=(0, 14))
        settings.columnconfigure(0, weight=1)
        monitor = tk.Frame(self.main_frame, bg="#0a0a0f")
        monitor.grid(row=2, column=1, sticky="nsew")
        monitor.columnconfigure(0, weight=1)
        monitor.rowconfigure(2, weight=1)

        def card(parent, heading, row):
            border = tk.Frame(parent, bg=panel, highlightbackground="#243044", highlightthickness=1)
            border.grid(row=row, column=0, sticky="nsew", pady=(0, 10 if row < 3 else 0))
            parent.rowconfigure(row, weight=1)
            inner = tk.Frame(border, bg=panel)
            inner.pack(fill="both", expand=True, padx=15, pady=10)
            tk.Label(inner, text=heading, font=("Consolas", 12, "bold"), bg=panel,
                     fg=accent).pack(anchor="w", pady=(0, 10))
            return inner

        def label(parent, caption):
            widget = tk.Label(parent, text=caption, font=("Microsoft YaHei UI", 11), bg=panel, fg=muted)
            widget.pack(side="left", padx=(0, 8))
            return widget

        def button(parent, caption, command):
            return tk.Button(parent, text=caption, command=command, font=font,
                             bg="#1a2637", fg=text, activebackground="#243e4c", activeforeground=accent,
                             relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
                             highlightthickness=1, highlightbackground="#30435a")

        task = card(settings, "01 / TASK & MODULE", 0)
        self.mode_var = tk.StringVar(value="总结知识点")
        mode_frame = tk.Frame(task, bg=panel)
        mode_frame.pack(fill="x", pady=(0, 5))
        self.mode_buttons = []
        for caption, value in (("SUMMARY  知识点总结", "总结知识点"), ("PRACTICE  题目练习", "练习")):
            widget = tk.Radiobutton(mode_frame, text=caption, variable=self.mode_var, value=value,
                                    indicatoron=False, bg="#182130", fg=muted, selectcolor="#153b39",
                                    activebackground="#1c4845", activeforeground=accent, font=("Microsoft YaHei UI", 12, "bold"),
                                    relief="flat", bd=0, padx=9, pady=6, cursor="hand2")
            widget.pack(side="left", fill="x", expand=True, padx=(0, 5 if not self.mode_buttons else 0))
            self.mode_buttons.append(widget)
        self.chapters = ["全部模块（一键生成 6 份）", *MODULE_RULES]
        self.chapter_var = tk.StringVar(value=self.chapters[1])
        chapter_frame = tk.Frame(task, bg=panel)
        chapter_frame.pack(fill="x", pady=(8, 0))
        label(chapter_frame, "模块")
        self.chapter_menu = ttk.Combobox(chapter_frame, textvariable=self.chapter_var, values=self.chapters,
                                        state="readonly", style="Cyber.TCombobox", font=font)
        self.chapter_menu.pack(side="left", fill="x", expand=True)

        self.engine_panel = card(settings, "02 / AI SERVICE", 1)
        self.ai_frame = tk.Frame(self.engine_panel, bg=panel)
        self.ai_frame.pack(fill="x")
        self.ai_var = tk.StringVar(value="GPT (Codex)")
        self.ai_menu = ttk.Combobox(self.ai_frame, textvariable=self.ai_var, values=list(AI_ADAPTERS),
                                   state="readonly", width=14, style="Cyber.TCombobox", font=font)
        self.ai_menu.pack(side="left")
        self.ai_menu.bind("<<ComboboxSelected>>", self.toggle_model_menu)
        tk.Label(self.ai_frame, text="方式", font=font, bg=panel, fg=muted).pack(side="left", padx=(9, 5))
        self.run_mode_var = tk.StringVar(value="CLI")
        self.run_mode_menu = ttk.Combobox(self.ai_frame, textvariable=self.run_mode_var,
                                         values=AI_RUN_MODES[self.ai_var.get()], state="readonly", width=5,
                                         style="Cyber.TCombobox", font=mono)
        self.run_mode_menu.pack(side="left")
        self.run_mode_menu.bind("<<ComboboxSelected>>", self.toggle_api_key)
        self.api_key_frame = tk.Frame(self.ai_frame, bg=panel)
        tk.Label(self.api_key_frame, text="API-Key", font=("Consolas", 11), bg=panel, fg=muted).pack(side="left", padx=(0, 4))
        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(self.api_key_frame, textvariable=self.api_key_var, show="*", width=9,
                                       style="Cyber.TEntry", font=mono)
        self.api_key_entry.pack(side="left", fill="x", expand=True)
        self.api_key_entry.bind("<FocusOut>", self.refresh_api_models)
        self.current_ai = self.ai_var.get()
        self.ai_settings, self.model_settings = {}, {}
        self.api_model_lists, self.model_requests = {}, set()
        self.model_context = (self.current_ai, self.run_mode_var.get())
        self.model_frame = tk.Frame(self.engine_panel, bg=panel)
        self.model_frame.pack(fill="x", pady=(12, 0))
        self.model_label = label(self.model_frame, "模型")
        self.refresh_models_btn = button(self.model_frame, "读取模型", self.refresh_api_models)
        self.cli_models = ["gpt-6.1-sol", "gpt-6-astra", "gpt-6-sol", "gpt-5.2"]
        self.model_var = tk.StringVar(value=self.cli_models[0])
        self.model_menu = ttk.Combobox(self.model_frame, textvariable=self.model_var, values=self.cli_models,
                                      state="readonly", style="Cyber.TCombobox", font=mono)
        self.model_menu.pack(side="left", fill="x", expand=True)

        export = card(settings, "03 / OUTPUT FORMAT", 2)
        self.output_format_var = tk.StringVar(value="PDF")
        self.output_format_menu = ttk.Combobox(export, textvariable=self.output_format_var, values=list(OUTPUT_FORMATS),
                                              state="readonly", style="Cyber.TCombobox", font=mono)
        self.output_format_menu.pack(fill="x")
        self.output_format_menu.bind("<<ComboboxSelected>>", self.toggle_output_format)
        pdf_frame = tk.Frame(export, bg=panel)
        pdf_frame.pack(fill="x", pady=(12, 0))
        label(pdf_frame, "PDF 引擎")
        self.pdf_engine_var = tk.StringVar(value="浏览器（推荐）")
        self.pdf_engine_menu = ttk.Combobox(pdf_frame, textvariable=self.pdf_engine_var, values=list(PDF_ENGINES),
                                           state="readonly", style="Cyber.TCombobox", font=font)
        self.pdf_engine_menu.pack(side="left", fill="x", expand=True)

        resources = card(settings, "04 / FILES & RESOURCES", 3)
        paths = tk.Frame(resources, bg=panel)
        paths.pack(fill="x")
        self.open_dir_btn = button(paths, "打开教材文件夹", self.open_textbook_dir)
        self.open_dir_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.open_output_btn = button(paths, "打开输出文件夹", self.open_output_dir)
        self.open_output_btn.pack(side="left", fill="x", expand=True)
        self.source_frame = tk.Frame(resources, bg=panel)
        self.open_sources_btn = button(self.source_frame, "真题来源  /  第 1–17 届", self.open_problem_sources)
        self.open_sources_btn.pack(fill="x")
        self.resource_tip = tk.Label(resources, font=("Microsoft YaHei UI", 11), bg=panel, fg=muted,
                                     anchor="w", justify="left", wraplength=470)
        self.resource_tip.pack(fill="x", pady=(8, 0))
        resources.bind("<Configure>", lambda event: self.resource_tip.config(wraplength=max(200, event.width)))

        actions = tk.Frame(monitor, bg=panel, highlightbackground="#243044", highlightthickness=1)
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(actions, text="[ EXECUTION CONTROL ]", font=("Consolas", 12, "bold"), bg=panel,
                 fg=accent).pack(anchor="w", padx=16, pady=(14, 10))
        self.run_btn = tk.Button(actions, text=">>> EXECUTE PROTOCOL <<<", font=("Consolas", 15, "bold"),
                                 bg=accent, fg="#071c1b", activebackground="#61ffe0", command=self.start_task,
                                 relief="flat", bd=0, pady=12, cursor="hand2")
        self.run_btn.pack(fill="x", padx=16, pady=(9, 14))
        self.fix_env_btn = button(actions, "一键配置环境", self.fix_environment)
        self.fix_env_btn.pack(fill="x", padx=16, before=self.run_btn)

        self.progress_frame = tk.Frame(monitor, bg=panel, highlightbackground="#243044", highlightthickness=1)
        self.progress_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        progress_header = tk.Frame(self.progress_frame, bg=panel)
        progress_header.pack(fill="x", padx=16, pady=(12, 6))
        self.status_label = tk.Label(progress_header, text="STATUS: IDLE", font=("Consolas", 12), bg=panel, fg="#00ff41", anchor="w", width=1)
        self.status_label.pack(side="left", fill="x", expand=True)
        self.percent_label = tk.Label(progress_header, text="0%", font=("Consolas", 12, "bold"), bg=panel, fg=accent)
        self.percent_label.pack(side="right")
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.progress_frame, variable=self.progress_var, maximum=100,
                                            style="Cyber.Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 12))

        terminal = tk.Frame(monitor, bg="#080d14", highlightbackground="#243044", highlightthickness=1)
        terminal.grid(row=2, column=0, sticky="nsew")
        terminal.columnconfigure(0, weight=1)
        terminal.rowconfigure(1, weight=1)
        terminal_header = tk.Frame(terminal, bg="#141d2b")
        terminal_header.grid(row=0, column=0, sticky="ew")
        tk.Label(terminal_header, text="●  LIVE OUTPUT", font=("Consolas", 12, "bold"), bg="#141d2b",
                 fg=accent).pack(side="left", padx=12, pady=10)
        self.task_badge = tk.Label(terminal_header, text="SUMMARY", font=("Consolas", 11), bg="#141d2b", fg=muted)
        self.task_badge.pack(side="right", padx=12)
        self.output_box = scrolledtext.ScrolledText(terminal, width=36, height=10, bg="#080d14", fg="#00ff41",
                                                   font=("Consolas", 12), insertbackground=accent, relief="flat", bd=0,
                                                   padx=12, pady=12, wrap="word", spacing1=2, spacing3=4)
        self.output_box.grid(row=1, column=0, sticky="nsew")
        self.output_box.vbar.configure(bg="#1c293b", troughcolor="#080d14", activebackground="#29435a", relief="flat", bd=0)
        self.mode_var.trace_add("write", self.toggle_task_mode)
        self.toggle_task_mode()
        self.root.after(100, self.poll_events)
        self.show_usage_hint()

    def ui(self, callback, *args, **kwargs):
        self.ui_events.put((callback, args, kwargs))

    def poll_events(self):
        try:
            for _ in range(100):
                callback, args, kwargs = self.ui_events.get_nowait()
                callback(*args, **kwargs)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.poll_events)

    def append_output(self, text):
        self.output_box.insert("end", text)
        self.output_box.see("end")

    def fix_environment(self):
        engine = PDF_ENGINES[self.pdf_engine_var.get()]
        output_format = OUTPUT_FORMATS[self.output_format_var.get()]
        run_mode = self.run_mode_var.get()
        ai = self.ai_var.get()
        api_key = self.api_key_var.get().strip() if run_mode == "API" else ""
        model_name = self.model_var.get()
        self.output_box.delete("1.0", "end")
        self.fix_env_btn.config(state="disabled")
        self.run_btn.config(state="disabled")
        self.log(f"正在配置 {ai} / {run_mode} 和 {self.output_format_var.get()} 输出环境...", "[FIX]")

        def run_fix():
            failures = []
            try:
                try:
                    configure_environment(engine, lambda message: self.log(message, "[FIX]"), output_format=output_format)
                    with tempfile.TemporaryDirectory(prefix="math-comp-env-") as work:
                        sample = Path(work) / "check.md"
                        sample.write_text(
                            "# 输出格式检查\n\n## 一、基础公式\n\n### 1. 极限的含义\n\n"
                            "这是首行缩进两个汉字的宋体四号正文，**关键条件应加粗**，标题应为黑体加粗。\n\n"
                            "- 中文列表\n\n由\n$$\n\\lim_{x\\to 0}\\frac{\\sin x}{x}\n=\n1\n$$\n"
                            "可知极限为 $1$。\n\n"
                            "$$\\boxed{a^2+b^2=c^2}$$\n\n"
                            "| 检查项 | 结果 |\n| --- | --- |\n| 表格 | 正常 |\n",
                            encoding="utf-8",
                        )
                        save_document(sample.read_text(encoding="utf-8"), Path(work) / "check", output_format, engine)
                    self.log(f"{output_format.upper()} 输出环境与实际文件导出检查通过。", "[FIX]")
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                    failures.append(output_format.upper())
                    self.log(f"输出环境配置未完成：{getattr(error, 'stderr', None) or error}", "[ERR]")
                try:
                    configure_ai(AI_PROVIDERS[ai], run_mode, lambda message: self.log(message, "[FIX]"), api_key, model_name)
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                    failures.append("AI")
                    self.log(f"{ai} / {run_mode} 配置未完成：{getattr(error, 'stderr', None) or error}", "[ERR]")
                if failures:
                    self.log("配置检查结束，仍需处理：" + "、".join(failures) + "。请查看上方对应错误。", "[WARN]")
                else:
                    self.log(f"{ai} / {run_mode} 与 {output_format.upper()} 输出环境配置均已完成。", "[FIX]")
            finally:
                self.ui(self.fix_env_btn.config, state="normal")
                self.ui(self.run_btn.config, state="normal")

        threading.Thread(target=run_fix, daemon=True).start()

    def open_textbook_dir(self):
        textbook_dir = os.path.join(BASE_DIR, "local_textbook")
        os.makedirs(textbook_dir, exist_ok=True)
        if os.name == 'nt':
            os.startfile(textbook_dir)
        else:
            subprocess.run(["open", textbook_dir])

    def open_output_dir(self):
        output_dir = os.path.join(BASE_DIR, "output")
        os.makedirs(output_dir, exist_ok=True)
        if os.name == 'nt':
            os.startfile(output_dir)
        else:
            subprocess.run(["open", output_dir])

    def open_problem_sources(self):
        if self.mode_var.get() != "练习":
            self.log("真题来源属于题目练习，请先切换至 PRACTICE。", "[TIP]")
            return
        self.open_sources_btn.config(state="disabled")
        self.log("正在核对第 1–17 届真题来源及访问限制；默认只建立索引，不批量保存 PDF。", "[TIP]")

        def load_index():
            try:
                report = open_source_index(log=lambda message: self.log(message, "[SOURCE]"))
                webbrowser.open(report.as_uri())
            except (OSError, ValueError, RuntimeError) as error:
                self.log(f"来源索引未完成：{error}", "[ERR]")
            finally:
                self.ui(self.open_sources_btn.config, state="normal")

        threading.Thread(target=load_index, daemon=True).start()

    def toggle_task_mode(self, *args):
        practice = self.mode_var.get() == "练习"
        self.chapters = [f"全部模块（一键生成 {7 if practice else 6} 份）", *MODULE_RULES]
        self.chapter_menu.config(values=self.chapters)
        if self.chapter_var.get().startswith("全部模块"):
            self.chapter_var.set(self.chapters[0])
        for button, value in zip(self.mode_buttons, ("总结知识点", "练习")):
            button.config(fg="#00ffcc" if self.mode_var.get() == value else "#8494aa")
        self.task_badge.config(text="PRACTICE" if practice else "SUMMARY")
        if practice:
            self.source_frame.pack(fill="x", pady=(8, 0), before=self.resource_tip)
            self.resource_tip.config(text="教材用于补充参考；练习另读取真题与开放题库，按非数 A 范围出题。")
            message = "已切换题目练习：两套各 5 道填空、5 道解答；此模式才读取真题与题库参考。"
        else:
            self.source_frame.pack_forget()
            self.resource_tip.config(text="教材可选：放入 local_textbook 优先参考；没有教材时，AI 直接总结知识点。")
            message = "已切换知识点总结：全面梳理、精炼表达并突出重点；批量生成前六模块，综合总结可单独选取。不读取真题或题库。"
        self.log(message, "[TIP]")

    def toggle_output_format(self, event=None):
        self.pdf_engine_menu.config(state="readonly" if self.output_format_var.get() == "PDF" else "disabled")
        hints = {"Word": "Word 输出为可编辑的 .docx；首次使用可点击一键配置环境安装 Pandoc。",
                 "PDF": "PDF 默认使用浏览器导出；选择专业排版时，一键配置会检查 LaTeX 环境。",
                 "MD": "MD 保存原始 Markdown，可继续编辑；字体、居中和公式效果取决于查看软件。",
                 "HTML": "HTML 可用浏览器打开，包含公式样式和字体，便于预览或打印。"}
        self.log(hints[self.output_format_var.get()], "[TIP]")

    def toggle_model_menu(self, event=None):
        self.ai_settings[self.current_ai] = (self.run_mode_var.get(), self.api_key_var.get())
        ai = self.ai_var.get()
        self.current_ai = ai
        run_modes = AI_RUN_MODES[ai]
        self.run_mode_menu.config(values=run_modes)
        default_mode = "CLI" if "CLI" in run_modes else run_modes[0]
        run_mode, api_key = self.ai_settings.get(ai, (default_mode, ""))
        self.run_mode_var.set(run_mode)
        self.api_key_var.set(api_key)
        self.toggle_api_key()

    def toggle_api_key(self, event=None):
        self.model_settings[self.model_context] = self.model_var.get()
        ai = self.ai_var.get()
        run_mode = self.run_mode_var.get()
        self.model_context = (ai, run_mode)
        if run_mode == "API":
            self.api_key_frame.pack(side="left", fill="x", expand=True, padx=(10, 0))
            provider = AI_PROVIDERS[ai]
            default_model = os.environ.get(API_SETTINGS[provider][3], "") if provider == "codex" else api_model(provider)
            self.model_label.config(text="模型 / 接入点" if ai == "豆包" else "API 模型 ID")
            context = self.api_model_context()
            self.model_menu.config(values=self.api_model_lists.get(context, [default_model] if default_model else ()), state="normal")
            self.model_var.set(self.model_settings.get(self.model_context, default_model))
            self.model_frame.pack(fill="x", after=self.ai_frame, pady=(12, 0))
            self.refresh_models_btn.pack(side="right", padx=(8, 0))
            pending = context in self.model_requests
            self.refresh_models_btn.config(state="disabled" if pending else "normal", text="读取中…" if pending else "读取模型")
            self.refresh_api_models(event=True)
        else:
            self.api_key_frame.pack_forget()
            self.refresh_models_btn.pack_forget()
            self.model_label.config(text="模型")
            self.model_menu.config(values=self.cli_models, state="readonly")
            self.model_var.set(self.model_settings.get(self.model_context, self.cli_models[0]))
            if ai == "GPT (Codex)" and run_mode == "CLI":
                self.model_frame.pack(fill="x", after=self.ai_frame, pady=(12, 0))
            else:
                self.model_frame.pack_forget()
        self.show_usage_hint()

    def api_model_context(self):
        provider = AI_PROVIDERS[self.ai_var.get()]
        key_variable, url_variable, default_url, _, _ = API_SETTINGS[provider]
        key = self.api_key_var.get().strip() or os.environ.get(key_variable, "").strip()
        return self.ai_var.get(), key, os.environ.get(url_variable, default_url)

    def refresh_api_models(self, event=None):
        if self.run_mode_var.get() != "API":
            return
        context = self.api_model_context()
        ai, key, _ = context
        if not key:
            if event is None:
                self.log("API-Key 用于账号认证；填好后点击“读取模型”向所选平台查询列表，再选择或手填模型 ID。", "[TIP]")
            return
        if context in self.model_requests or (event is not None and context in self.api_model_lists):
            return
        self.model_requests.add(context)
        self.refresh_models_btn.config(state="disabled", text="读取中…")

        def finish(models, error):
            self.model_requests.discard(context)
            if models:
                self.api_model_lists[context] = models
            if self.run_mode_var.get() != "API" or self.api_model_context() != context:
                return
            self.refresh_models_btn.config(state="normal", text="读取模型")
            if error:
                self.log(f"模型列表读取失败：{error}。仍可手动输入模型或接入点 ID。", "[WARN]")
            else:
                self.model_menu.config(values=models)
                self.log(f"已读取 {ai} 的 {len(models)} 个模型；请从下拉框选择，或手动输入 ID。", "[TIP]")

        def load():
            try:
                models = list_api_models(AI_PROVIDERS[ai], key)
                self.ui(finish, models, None)
            except (OSError, ValueError, RuntimeError) as error:
                self.ui(finish, None, str(error))

        threading.Thread(target=load, daemon=True).start()

    def show_usage_hint(self):
        ai = self.ai_var.get()
        run_mode = self.run_mode_var.get()
        if run_mode == "GUI":
            message = "首次使用需在弹出的浏览器中登录 ChatGPT，并在网页中选择模型；登录窗口会保留。"
        elif run_mode == "API":
            message = f"{ai} API：请先填写 Key 和模型 ID，再点击配置；“读取模型”可查询账号模型列表。"
        else:
            message = "Codex CLI 安装完成后，在终端运行 codex login 完成首次登录。"
        self.log("首次使用：选好 AI、运行方式和输出格式后，点击右上方“一键配置环境”，即可自动安装并检查所需工具。" + message, "[TIP]")

    def log(self, text, prefix="[SYS]"):
        timestamp = time.strftime("%H:%M:%S")
        formatted_text = f"[{timestamp}] {prefix} {text}\n"
        self.ui(self.append_output, formatted_text)

    def update_progress(self, percent, stage):
        # 失败重试时保持已完成的进度；只有开始新队列时归零。
        percent = self.progress_var.get() if percent is None else max(self.progress_var.get(), min(100, max(0, percent)))
        self.progress_var.set(percent)
        self.status_label.config(text=stage)
        self.percent_label.config(text=f"{percent:.0f}%")
        self.root.title(f"MATH COMP // {stage}")

    def start_task(self):
        mode = self.mode_var.get()
        chapter = self.chapter_var.get() 
        ai = self.ai_var.get()
        model_name = self.model_var.get()
        pdf_engine = PDF_ENGINES[self.pdf_engine_var.get()]
        output_format = OUTPUT_FORMATS[self.output_format_var.get()]
        
        self.output_box.delete("1.0", "end")
        self.show_usage_hint()
        run_mode = self.run_mode_var.get()
        api_key = self.api_key_var.get().strip() if run_mode == "API" else ""
        if run_mode == "API":
            if not api_key and not os.environ.get(API_SETTINGS[AI_PROVIDERS[ai]][0]):
                self.log("请先填写 API-Key。", "[WARN]")
                self.api_key_entry.focus_set()
                return
            if not model_name.strip():
                self.log("请填写 API 模型 ID；豆包可填写推理接入点 ID。", "[WARN]")
                self.model_menu.focus_set()
                return
            try:
                api_key, model_name, _ = validate_api_configuration(
                    AI_PROVIDERS[ai], key=api_key or os.environ.get(API_SETTINGS[AI_PROVIDERS[ai]][0], ""),
                    model=model_name,
                )
            except ValueError as error:
                self.log(str(error), "[WARN]")
                self.api_key_entry.focus_set()
                return
        self.run_btn.config(state="disabled", text=">>> GENERATING... <<<", bg="#555555")
        self.fix_env_btn.config(state="disabled")
        self.progress_var.set(0)
        self.percent_label.config(text="0%")
        self.status_label.config(text="STATUS: INITIALIZING...")
        
        target_chapters = []
        if chapter.startswith("全部模块"):
            target_chapters = list(MODULE_RULES)[:6 if mode == "总结知识点" else 7]
        else:
            target_chapters = [chapter]

        threading.Thread(target=self.run_all_tasks, args=(ai, mode, target_chapters, model_name, pdf_engine, run_mode, api_key, output_format), daemon=True).start()

    def run_all_tasks(self, ai, mode, chapters, model_name, pdf_engine="browser", run_mode="CLI", api_key="", output_format="pdf"):
        total = len(chapters)
        successes = 0
        processed = 0
        try:
            self.ui(self.update_progress, 2, "检查运行环境")
            check_output_environment(output_format, pdf_engine)
            self.ui(self.update_progress, 5, "准备读取教材")
            output_dir = os.path.join(BASE_DIR, "output")
            os.makedirs(output_dir, exist_ok=True)
            textbook_files = sorted(glob.glob(os.path.join(BASE_DIR, "local_textbook", "*.pdf")))
            extract_script = os.path.join(BASE_DIR, "skills", "math-comp-prep", "scripts", "extract_pdf.py")
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
                        with subprocess.Popen(
                            [sys.executable, "-u", extract_script, pdf_path, "--output", str(text_path)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", env=env,
                        ) as process:
                            for line in process.stdout:
                                progress = parse_progress(line)
                                if progress:
                                    value, stage = progress
                                    self.ui(self.update_progress, 5 + 20 * (book_index + value / 100) / len(textbook_files),
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
                    self.ui(self.update_progress, 5 + 20 * (book_index + 1) / len(textbook_files), "教材读取阶段完成")
            self.ui(self.update_progress, 25, "准备生成正文")
            if not textbook_texts:
                self.log("没有可用的教材文本，AI 将基于自身知识生成。", "[WARN]")

            for i, chap in enumerate(chapters):
                task_start, task_share = 25 + 75 * i / total, 75 / total
                self.ui(self.update_progress, task_start, f"模块 {i + 1}/{total} · 整理参考资料")
                self.log(f"队列进度 [{i+1}/{total}] 开始处理: {chap}", "[QUEUE]")
                try:
                    keywords = MODULE_RULES[chap][1]
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
                    cmd = [sys.executable, "-u", AI_ADAPTERS[ai], prompt, os.path.join(output_dir, safe_name)]
                    if ai == "GPT (Codex)" and run_mode == "CLI":
                        cmd.append(model_name)
                    cmd.extend(["--pdf-engine", pdf_engine, "--run-mode", run_mode, "--output-format", output_format])
                    adapter_env = env.copy()
                    if run_mode == "API":
                        cmd.extend(["--api-model", model_name])
                        if api_key:
                            adapter_env["MATH_COMP_API_KEY"] = api_key
                    with subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace", env=adapter_env, cwd=BASE_DIR,
                    ) as process:
                        for line in process.stdout:
                            progress = parse_progress(line)
                            if progress:
                                value, stage = progress
                                self.ui(self.update_progress, task_start + task_share * value / 100,
                                        f"模块 {i + 1}/{total} · {stage}")
                            else:
                                self.ui(self.append_output, line)
                        return_code = process.wait()
                    if return_code:
                        self.log(f"失败: {chap}（退出码 {return_code}）", "[ERR]")
                    else:
                        successes += 1
                        self.log(f"完成: {chap}", "[DONE]")
                except Exception as error:
                    self.log(f"执行失败: {chap}: {error}", "[ERR]")
                finally:
                    processed = i + 1
                    self.ui(self.update_progress, task_start + task_share, f"已处理 {processed}/{total} 个模块")
        except Exception as error:
            self.log(f"队列执行失败: {error}", "[ERR]")
        finally:
            status = "全部完成" if total and successes == total else "任务结束，存在失败项"
            self.ui(self.update_progress, 100 if total and processed == total else None, status)
            self.log(f"队列结束：成功 {successes} 项，失败 {total - successes} 项。成功文件保存在 output 文件夹。")
            self.ui(self.run_btn.config, state="normal", text=">>> EXECUTE PROTOCOL <<<", bg="#00ffcc")
            self.ui(self.fix_env_btn.config, state="normal")

if __name__ == "__main__":
    root = tk.Tk()
    app = MathApp(root)
    root.mainloop()

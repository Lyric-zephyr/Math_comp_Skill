"""Shared API, CLI and GUI generation for the existing platform adapters."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.error
import urllib.request

if __package__:
    from .skill_rules import ALL_MODULE_RULES, SUBJECT_MODULES, SUMMARY_TOPICS, subject_for_chapter, build_prompt
    from .task_progress import report_progress
else:
    from skill_rules import ALL_MODULE_RULES, SUBJECT_MODULES, SUMMARY_TOPICS, subject_for_chapter, build_prompt
    from task_progress import report_progress


MODELS = json.loads((Path(__file__).resolve().parent.parent / "models.json").read_text(encoding="utf-8"))
API_SETTINGS = {
    "codex": ("OPENAI_API_KEY", "OPENAI_BASE_URL", "https://api.openai.com/v1", "OPENAI_MODEL", MODELS["api"]["codex"]),
    "dsh": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "https://api.deepseek.com", "DEEPSEEK_MODEL", MODELS["api"]["dsh"]),
    "doubao": ("ARK_API_KEY", "ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3", "ARK_MODEL", MODELS["api"]["doubao"]),
}
RUN_MODES = {"codex": ("GUI", "CLI", "API"), "dsh": ("API",), "doubao": ("API",)}
PROVIDER_NAMES = {"codex": "Codex", "dsh": "DeepSeek (DSH)", "doubao": "豆包"}
# 本进程内所有 API 调用的 token 累计，随生成结果一起报告。
USAGE = {"input": 0, "output": 0, "calls": 0}


def api_model(provider):
    _, _, _, variable, default = API_SETTINGS[provider]
    return os.environ.get(variable, default)


def validate_api_configuration(provider, key=None, model=None, require_model=True):
    """先检查本地配置，避免识别完整本教材后才因请求头编码失败。"""
    key_variable, url_variable, default_url, _, _ = API_SETTINGS[provider]
    if key is None:
        key = os.environ.get("MATH_COMP_API_KEY") or os.environ.get(key_variable, "")
    key = key.strip()
    if not key:
        raise ValueError(f"请填写 API-Key，或设置 {key_variable}。")
    if any(not 33 <= ord(character) <= 126 for character in key):
        raise ValueError("API-Key 含中文、空格或不可见字符。请从平台复制真实密钥，只粘贴 Key，不要包含说明文字、引号或 Bearer 前缀。")
    if key.startswith(("'", '"')) or key.endswith(("'", '"')):
        raise ValueError("API-Key 两端含引号，请只粘贴平台生成的密钥。")
    model = (api_model(provider) if model is None else model).strip()
    if require_model and not model:
        raise ValueError("请填写 API 模型 ID；豆包也可填写推理接入点 ID。")
    base_url = os.environ.get(url_variable, default_url).strip().rstrip("/")
    if not base_url.startswith("https://") and not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError(f"{url_variable} 必须使用 HTTPS。")
    if any(not 33 <= ord(character) <= 126 for character in base_url):
        raise ValueError(f"{url_variable} 含中文、空白或不可见字符，请填写平台提供的 API 服务地址。")
    return key, model, base_url


def list_api_models(provider, key, timeout=15):
    """读取账号可见模型，不发送生成请求；实际权限仍由服务商决定。"""
    key, _, base_url = validate_api_configuration(provider, key=key, require_model=False)
    request = urllib.request.Request(base_url + "/models", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}，请检查 API-Key、服务地址及模型列表接口权限") from None
    except urllib.error.URLError as error:
        raise RuntimeError(str(error.reason).replace(key, "[已隐藏]")) from None
    except UnicodeEncodeError:
        raise ValueError("API 请求头编码失败，请检查 API-Key 和代理配置是否混入中文或特殊字符。") from None
    if not isinstance(result, dict) or not isinstance(result.get("data"), list):
        raise ValueError("服务没有提供兼容的模型列表格式")
    models = sorted({item["id"] for item in result.get("data", [])
                     if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]})
    if provider == "codex":
        models = [model for model in models if model.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4"))
                  and not any(kind in model for kind in ("audio", "realtime", "transcribe", "tts", "image"))]
    if not models:
        raise ValueError("服务未返回可用的文本模型列表")
    return models


def add_runtime_arguments(parser):
    parser.add_argument("--provider", choices=tuple(API_SETTINGS), required=True, help="codex、dsh（DeepSeek）或 doubao（豆包）")
    parser.add_argument("--run-mode", choices=("GUI", "CLI", "API"), help="默认：codex 为 CLI，其余为 API")
    parser.add_argument("--api-model", help="API 模型 ID；豆包也可填写推理接入点 ID")
    parser.add_argument("--cli-model", default=MODELS["cli"][0], help="Codex CLI 模型名称")
    parser.add_argument("--timeout", type=int, default=1200, help="等待 AI 完成的最长秒数")
    parser.add_argument("--prompt-file", type=Path, help="读取 UTF-8 提示词文件，避免命令行长度限制")
    parser.add_argument("--task-mode", choices=("summary", "practice"), help="为直接运行适配器加载对应 skill 规则")
    parser.add_argument("--chapter", choices=tuple(ALL_MODULE_RULES), help="与 --task-mode 一起指定模块")


def _record_usage(usage):
    if not isinstance(usage, dict):
        return
    USAGE["calls"] += 1
    for key, names in (("input", ("input_tokens", "prompt_tokens")), ("output", ("output_tokens", "completion_tokens"))):
        value = next((usage[name] for name in names if isinstance(usage.get(name), int)), 0)
        USAGE[key] += value


def _message_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part["text"] for part in content
                         if isinstance(part, dict) and isinstance(part.get("text"), str))
    return ""


def generate_api(provider, prompt, model=None, timeout=1200):
    key, model, base_url = validate_api_configuration(provider, model=model)

    if provider == "codex":
        endpoint = "/responses"
        payload = {"model": model, "input": prompt, "store": False}
    else:
        endpoint = "/chat/completions"
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False}
    request = urllib.request.Request(
        base_url + endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(details).get("error", {})
            details = message.get("message", str(message)) if isinstance(message, dict) else str(message)
        except (ValueError, AttributeError):
            details = error.reason
        raise RuntimeError(f"API 请求失败（HTTP {error.code}）：{str(details).replace(key, '[已隐藏]')}") from None
    except urllib.error.URLError as error:
        raise RuntimeError(f"无法连接 API：{str(error.reason).replace(key, '[已隐藏]')}") from None
    except UnicodeEncodeError:
        raise ValueError("API 请求头编码失败，请检查 API-Key 和代理配置是否混入中文或特殊字符。") from None

    if not isinstance(result, dict):
        raise ValueError("API 返回格式异常：预期为 JSON 对象。")
    _record_usage(result.get("usage"))
    if result.get("error"):
        raise RuntimeError(f"API 返回错误：{str(result['error']).replace(key, '[已隐藏]')}")
    if provider == "codex":
        if result.get("status") != "completed":
            raise RuntimeError("API 回答未完成：" + str(result.get("incomplete_details") or result.get("status")))
        output = result.get("output")
        if not isinstance(output, list):
            raise ValueError("API 返回格式异常：缺少有效的 output 列表。")
        content = "\n".join(_message_text(item.get("content")) for item in output
                            if isinstance(item, dict) and item.get("type") == "message")
    else:
        choices = result.get("choices") or []
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("API 没有返回有效的回答列表。")
        choice = choices[0]
        if choice.get("finish_reason") not in (None, "stop"):
            raise RuntimeError(f"API 回答未完成：{choice.get('finish_reason')}，请检查输出长度或内容限制。")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ValueError("API 返回格式异常：缺少有效的回答内容。")
        content = _message_text(message.get("content"))
    if not content.strip():
        raise ValueError("API 返回了空正文，请检查模型是否支持文本输出。")
    return content.strip()


def generate_content(provider, args, base_dir):
    if getattr(args, "prompt_file", None):
        args.prompt = args.prompt_file.read_text(encoding="utf-8-sig")
    if args.run_mode is None:
        args.run_mode = "CLI" if provider == "codex" else "API"
    if args.run_mode not in RUN_MODES[provider]:
        raise ValueError("该平台不支持所选运行方式。")
    if args.timeout <= 0:
        raise ValueError("等待时间必须大于零。")
    if bool(args.task_mode) != bool(args.chapter):
        raise ValueError("--task-mode 和 --chapter 必须一起提供。")
    if args.task_mode:
        mode = "总结知识点" if args.task_mode == "summary" else "练习"
        args.prompt = build_prompt(mode, args.chapter, args.prompt)
    print(f"[*] 运行方式：{args.run_mode}", flush=True)
    report_progress(5, "准备生成正文")
    summary = args.task_mode == "summary" or (not args.task_mode and "任务：【总结知识点】" in args.prompt[:512])
    if summary:
        match = re.search(r"章节：【([^】]+)】", args.prompt[:512])
        chapter = args.chapter or (match[1] if match else None)
        if chapter not in ALL_MODULE_RULES:
            raise ValueError("知识点总结需要有效模块。")
        return _generate_summary(chapter, args.prompt,
                                 lambda prompt: _generate_once(provider, args, base_dir, prompt))
    practice = args.task_mode == "practice" or (not args.task_mode and "任务：【练习】" in args.prompt[:512])
    if practice:
        if __package__:
            from .practice_history import ask_user, generate_practice
        else:
            from practice_history import ask_user, generate_practice
        chapter = args.chapter
        if not chapter:
            match = re.search(r"章节：【([^】]+)】", args.prompt[:512])
            chapter = match[1] if match else None
        if chapter not in ALL_MODULE_RULES:
            raise ValueError("练习避重需要有效模块；直接调用请同时提供 --task-mode practice 和 --chapter。")
        return generate_practice(chapter, args.prompt,
                                 lambda prompt: _generate_once(provider, args, base_dir, prompt),
                                 directory=Path(base_dir) / "local_practice", ask=ask_user)
    content = _generate_once(provider, args, base_dir, args.prompt)
    report_progress(85, "正文生成完成")
    return content


def _generate_summary(chapter, prompt, generate, progress=None):
    """Generate disjoint subject topics, then one concise error section per module."""
    chapters = list(SUBJECT_MODULES[subject_for_chapter(chapter)])
    if progress is None:
        total_parts = sum(len(SUMMARY_TOPICS[c]) + 1 for c in chapters[:-1]) + 1 if chapter == chapters[-1] else len(SUMMARY_TOPICS[chapter]) + 1
        completed = 0

        def progress(stage):
            nonlocal completed
            completed += 1
            report_progress(5 + 80 * completed / total_parts, f"总结分段完成 {completed}/{total_parts} · {stage}")

    if chapter == chapters[-1]:
        # Rebuild each module's references without feeding the combined library back as user PDF.
        context = prompt.partition("【用户 PDF 教材（最高优先）】\n")[2].partition("\n\n【Assistant_course 课程库（次优先）】")[0]
        parts = []
        for current in chapters[:-1]:
            print(f"[*] 综合总结：正在完整整理 {current}", flush=True)
            body = _generate_summary(current, build_prompt("总结知识点", current, context), generate, progress)
            body = re.sub(r"(?m)^(#{2,5})(?=\s)", r"#\1", body)
            parts.append(f"## {current}\n\n{body}")
        parts.append(_generate_summary_part(prompt, "跨模块联系与方法选择", generate))
        progress("跨模块联系")
        return "\n\n".join(parts) + "\n"

    parts, covered = [], []
    for topics in SUMMARY_TOPICS[chapter]:
        print(f"[*] 知识点总结：{chapter} / {topics}", flush=True)
        instruction = (f"本轮只覆盖这些互相关联的主题：{topics}。不输出易错总结。"
                       "前轮已完成的主题如下，不得重述；需要衔接只作简短指代：\n" + "\n".join(covered))
        body = _generate_summary_part(prompt, "一、知识梳理", generate, instruction)
        parts.append(re.sub(r"\A##[^\n]*\n+", "", body))
        covered.extend(re.findall(r"(?m)^#{3,4}[ \t]+(.+)$", body))
        progress(topics)
    # Renumber subheadings across the generated topic groups.
    number = 0

    def renumber(match):
        nonlocal number
        number += 1
        return f"### {number}. {match[1]}"

    body = re.sub(r"(?m)^###[ \t]+(?:\d+[.、．][ \t]*)?(.+)$", renumber, "\n\n".join(parts))
    errors = _generate_summary_part(prompt, "二、易错总结", generate,
                "仅输出本模块 7–10 条易错提醒。已覆盖主题：\n" + "\n".join(covered))
    progress("易错总结")
    return f"## 一、知识梳理\n\n{body}\n\n{errors}\n"


def _generate_summary_part(prompt, heading, generate, scope=""):
    instruction = f"\n\n【分段执行】本轮仅输出 `## {heading}` 及其内容，不输出总标题、目录或其他大节。\n" + scope
    for attempt in range(2):
        try:
            body = generate(prompt + instruction).strip()
            body = re.sub(r"\A#[ \t]+[^\n]*\n+", "", body)
            if not body:
                raise RuntimeError("知识点分段返回空正文。")
            headings = re.findall(r"(?m)^##[ \t]+(.+?)\s*$", body)
            if headings and headings != [heading]:
                raise RuntimeError(f"知识点分段结构不正确，应只包含：{heading}。")
            if not headings:
                body = f"## {heading}\n\n{body}"
            if __package__:
                from .pdf_export import normalize_document
            else:
                from pdf_export import normalize_document
            body = normalize_document(body)
            if heading == "二、易错总结":
                numbers = re.findall(r"(?m)^(\d+)\.[^\n：:]+[：:]", body)
                if not 7 <= len(numbers) <= 10 or numbers != [str(number) for number in range(1, len(numbers) + 1)]:
                    raise RuntimeError("易错总结应包含 7–10 条连续编号的普通段落，格式为 1.标题：正文。")
            return body
        except (RuntimeError, subprocess.TimeoutExpired):
            if attempt:
                raise
            print(f"[!] {heading}生成未完成，正在重试本部分；已完成部分不会重新生成。", flush=True)


def save_generated_document(provider, args, base_dir, content):
    """只修复报错公式并重新导出，不重新出题或生成整篇正文。"""
    if __package__:
        from .document_export import save_document
        from .pdf_export import transform_math
    else:
        from document_export import save_document
        from pdf_export import transform_math

    def repair(current, error):
        report_progress(92, "修复公式并重新导出")
        formulas = list(dict.fromkeys(error.formulas))
        prompt = (
            "修复下列公式的 KaTeX/LaTeX 语法或超宽排版；过宽用 gathered 在等号、加减号或逻辑分隔处合理断行，每行各自居中，不用 & 对齐，禁止缩小字号；分隔逗号放在红框外且不重复。只返回 JSON 数组，每项包含 old 和 new 两个字符串；"
            "old 必须逐字等于输入公式，new 为修复后的公式，不带 $ 或其他数学定界符。"
            "保留数学含义、符号、条件和数值，只修复语法与换行，不重新解题或修改正文。"
            "反斜杠按 JSON 规范转义；每个输入公式必须对应一项。\n"
            + json.dumps({"formulas": formulas, "error": str(error)}, ensure_ascii=False)
        )
        reply = _generate_once(provider, args, base_dir, prompt).strip()
        reply = re.sub(r"\A```(?:json)?\s*|\s*```\Z", "", reply)
        patches = json.loads(reply)
        if (not isinstance(patches, list) or len(patches) != len(formulas)
                or any(not isinstance(item, dict) or not isinstance(item.get("old"), str)
                       or not isinstance(item.get("new"), str) or not item["new"].strip() for item in patches)
                or {item["old"] for item in patches} != set(formulas)):
            raise ValueError("AI 公式修复结果格式不完整，原文已保留。")
        # 仅替换完整匹配的数学片段，避免误改包含相同前缀的正确公式。
        replacements = {item["old"]: item["new"] for item in patches}
        if any(formula not in current for formula in formulas):
            raise ValueError("报错公式与原文不匹配，停止自动修改并保留原文。")

        def replace_formula(text):
            width = 2 if text.startswith(("$$", r"\(", r"\[")) else 1
            formula = text[width:-width]
            return text[:width] + replacements.get(formula, formula) + text[-width:]

        return transform_math(current, replace_formula)

    report_progress(90, f"正在导出 {args.output_format.upper()}")
    document = save_document(content, args.filename_prefix, args.output_format, args.pdf_engine, repair=repair)
    report_progress(100, "文档已保存")
    return document


def usage_line():
    """供启动器解析的 token 用量；非 API 方式没有用量数据。"""
    return "[USAGE] " + json.dumps(USAGE) if USAGE["calls"] else None


def _generate_once(provider, args, base_dir, prompt):
    if args.run_mode == "API":
        return generate_api(provider, prompt, args.api_model, args.timeout)
    if args.run_mode == "GUI":
        if __package__:
            from .gui_runtime import generate_gui
        else:
            from gui_runtime import generate_gui
        return generate_gui(provider, prompt, args.timeout)

    backend = shutil.which("codex")
    if not backend:
        raise FileNotFoundError("找不到 codex 命令，请先安装并登录 Codex CLI。")
    command = [backend, "exec", "--model", args.cli_model, "--sandbox", "read-only", "--skip-git-repo-check", "-"]
    result = subprocess.run(
        command, input=prompt, cwd=Path(base_dir), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=args.timeout, check=True,
    )
    return result.stdout.strip()

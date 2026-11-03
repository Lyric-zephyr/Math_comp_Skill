"""Shared API, CLI and GUI generation for the existing platform adapters."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.error
import urllib.request

if __package__:
    from .skill_rules import MODULE_RULES, build_prompt
else:
    from skill_rules import MODULE_RULES, build_prompt


API_SETTINGS = {
    "codex": ("OPENAI_API_KEY", "OPENAI_BASE_URL", "https://api.openai.com/v1", "OPENAI_MODEL", "gpt-5.2"),
    "dsh": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "https://api.deepseek.com", "DEEPSEEK_MODEL", "deepseek-flash"),
    "doubao": ("ARK_API_KEY", "ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3", "ARK_MODEL", "doubao-seed-2-1-pro-260915"),
}
RUN_MODES = {"codex": ("GUI", "CLI", "API"), "dsh": ("API",), "doubao": ("API",)}


def api_model(provider):
    _, _, _, variable, default = API_SETTINGS[provider]
    return os.environ.get(variable, default)


def list_api_models(provider, key, timeout=15):
    """读取账号可见模型，不发送生成请求；实际权限仍由服务商决定。"""
    _, url_variable, default_url, _, _ = API_SETTINGS[provider]
    base_url = os.environ.get(url_variable, default_url).rstrip("/")
    if not base_url.startswith("https://") and not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError(f"{url_variable} 必须使用 HTTPS。")
    request = urllib.request.Request(base_url + "/models", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}，请检查 API-Key、服务地址及模型列表接口权限") from None
    except urllib.error.URLError as error:
        raise RuntimeError(str(error.reason).replace(key, "[已隐藏]")) from None
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


def add_runtime_arguments(parser, provider):
    defaults = {"codex": "CLI", "dsh": "API", "doubao": "API"}
    parser.add_argument("--run-mode", choices=RUN_MODES[provider], default=defaults[provider])
    parser.add_argument("--api-model", help="API 模型 ID；豆包也可填写推理接入点 ID")
    parser.add_argument("--timeout", type=int, default=1200, help="等待 AI 完成的最长秒数")
    parser.add_argument("--task-mode", choices=("summary", "practice"), help="为直接运行适配器加载对应 skill 规则")
    parser.add_argument("--chapter", choices=tuple(MODULE_RULES), help="与 --task-mode 一起指定模块")


def _message_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part["text"] for part in content
                         if isinstance(part, dict) and isinstance(part.get("text"), str))
    return ""


def generate_api(provider, prompt, model=None, timeout=1200):
    key_variable, url_variable, default_url, _, _ = API_SETTINGS[provider]
    key = os.environ.get("MATH_COMP_API_KEY") or os.environ.get(key_variable, "")
    key = key.strip()
    if not key:
        raise ValueError(f"请填写 API-Key，或设置 {key_variable}。")
    model = (model or api_model(provider)).strip()
    if not model:
        raise ValueError("请填写 API 模型 ID。")
    base_url = os.environ.get(url_variable, default_url).rstrip("/")
    if not base_url.startswith("https://") and not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError(f"{url_variable} 必须使用 HTTPS。")

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

    if not isinstance(result, dict):
        raise ValueError("API 返回格式异常：预期为 JSON 对象。")
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
    if args.run_mode == "API":
        return generate_api(provider, args.prompt, args.api_model, args.timeout)
    if args.run_mode == "GUI":
        if __package__:
            from .gui_runtime import generate_gui
        else:
            from gui_runtime import generate_gui
        return generate_gui(provider, args.prompt, args.timeout)

    backend = shutil.which("codex")
    if not backend:
        raise FileNotFoundError("找不到 codex 命令，请先安装并登录 Codex CLI。")
    command = [backend, "exec", "--model", args.model_name, "--sandbox", "read-only", "--skip-git-repo-check", "-"]
    result = subprocess.run(
        command, input=args.prompt, cwd=Path(base_dir), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=args.timeout, check=True,
    )
    return result.stdout.strip()

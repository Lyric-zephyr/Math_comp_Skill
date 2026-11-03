"""Configure the selected AI method and PDF tools on explicit setup."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .pdf_export import check_environment, find_browser
from .document_export import OUTPUT_FORMATS, check_output_environment
from .ai_runtime import API_SETTINGS, RUN_MODES, api_model
from .tool_paths import find_tool, tool_environment


def refresh_path():
    """Let this process see tools added to PATH by Windows installers."""
    if os.name != "nt":
        return
    import winreg

    paths = os.environ.get("PATH", "").split(os.pathsep)
    for root, key in (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    ):
        try:
            with winreg.OpenKey(root, key) as registry:
                paths.extend(os.path.expandvars(winreg.QueryValueEx(registry, "Path")[0]).split(os.pathsep))
        except OSError:
            pass
    os.environ["PATH"] = os.pathsep.join(dict.fromkeys(path for path in paths if path))


def _run(command, log, timeout=1200, success_codes=(0,)):
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        env=tool_environment(command[0]),
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode not in success_codes:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"{command[0]} 执行失败（{result.returncode}）：{details}")
    if result.stdout.strip():
        log(result.stdout.strip())
    return result.returncode


def _install(package, log):
    if os.name != "nt" or not shutil.which("winget"):
        raise RuntimeError(f"无法自动安装 {package}：需要 Windows 的 WinGet（应用安装程序），或手动安装该工具。")
    log(f"正在安装 {package}，首次下载可能需要几分钟；如系统提示管理员授权，请按提示操作。")
    _run([
        "winget", "install", "--id", package, "--exact", "--source", "winget", "--silent",
        "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity", "--no-upgrade",
    ], log)
    refresh_path()


def configure_environment(engine="browser", log=print, output_format="pdf"):
    if output_format not in OUTPUT_FORMATS.values():
        raise ValueError(f"未知输出格式：{output_format}")
    if engine not in ("browser", "latex"):
        raise ValueError(f"未知 PDF 导出方式：{engine}")
    refresh_path()
    if importlib.util.find_spec("pymupdf") is None:
        log("正在安装教材文本提取工具 PyMuPDF...")
        _run([sys.executable, "-m", "pip", "install", "PyMuPDF"], log)

    if output_format == "md":
        log("Markdown 输出已就绪，无需额外排版工具。")
        return
    if output_format == "word":
        if not find_tool("pandoc"):
            _install("JohnMacFarlane.Pandoc", log)
        log(f"Word 导出工具已就绪：{check_output_environment('word')}")
        return
    if output_format == "html":
        engine = "browser"

    if engine == "browser":
        try:
            find_browser()
        except FileNotFoundError:
            if os.environ.get("MATH_COMP_BROWSER"):
                raise
            _install("Microsoft.Edge", log)
    else:
        for tool, package in (("pandoc", "JohnMacFarlane.Pandoc"), ("xelatex", "MiKTeX.MiKTeX")):
            if not find_tool(tool):
                _install(package, log)
            path = find_tool(tool)
            if not path:
                raise FileNotFoundError(f"安装后仍未找到 {tool}，请通过 MATH_COMP_{tool.upper()} 指定可执行文件路径。")
            log(f"已找到 {tool}：{path}")
        initexmf = find_tool("initexmf")
        miktex = find_tool("miktex")
        if initexmf:
            log("正在启用 MiKTeX 自动安装缺失宏包...")
            _run([initexmf, "--set-config-value=[MPM]AutoInstall=1"], log)
        if miktex:
            log("正在检查 MiKTeX 更新...")
            try:
                # MiKTeX uses 100 to report that package updates are available.
                status = _run([miktex, "packages", "check-update"], log, timeout=120, success_codes=(0, 100))
                if status == 100:
                    log("正在更新 MiKTeX 宏包...")
                    _run([miktex, "packages", "update"], log)
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                log(f"MiKTeX 更新未完成：{error}；继续检查本地 PDF 编译是否可用。")
        if initexmf:
            _run([initexmf, "--update-fndb"], log)

    tool = check_environment(engine)
    log(f"排版工具已就绪：{tool}")


def configure_gui(log=print):
    if importlib.util.find_spec("playwright") is None:
        log("正在安装 GUI 网页自动化工具 Playwright...")
        _run([sys.executable, "-m", "pip", "install", "playwright"], log)
    try:
        browser = find_browser()
    except FileNotFoundError:
        if os.environ.get("MATH_COMP_BROWSER"):
            raise
        _install("Microsoft.Edge", log)
        browser = find_browser()
    log(f"GUI 浏览器已就绪：{browser}；首次生成时请在浏览器内登录。")


def configure_ai(provider, run_mode, log=print, api_key="", model=None):
    if provider not in RUN_MODES or run_mode not in RUN_MODES[provider]:
        raise ValueError("该平台不支持所选运行方式。")
    refresh_path()
    if run_mode == "GUI":
        configure_gui(log)
        from playwright.sync_api import sync_playwright, Error as PlaywrightError
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=find_browser(), headless=True)
                browser.close()
        except PlaywrightError as error:
            raise RuntimeError(f"GUI 浏览器启动检查失败：{error}") from None
        log("GUI 自动化启动检查通过；网站登录和验证在生成时完成。")
    elif run_mode == "API":
        key_variable, url_variable, default_url, _, _ = API_SETTINGS[provider]
        if not (api_key or os.environ.get(key_variable, "")).strip():
            raise ValueError(f"请填写 API-Key，或设置 {key_variable}，然后重新点击配置。")
        if not (model if model is not None else api_model(provider)).strip():
            raise ValueError("请填写 API 模型 ID；豆包也可填写推理接入点 ID。")
        base_url = os.environ.get(url_variable, default_url)
        if not base_url.startswith("https://") and not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError(f"{url_variable} 必须使用 HTTPS。")
        log("API 本地配置检查通过：Key、模型和地址已填写；网络、密钥有效性及账户权限在生成时验证。")
    else:
        if not shutil.which("codex"):
            if not shutil.which("npm"):
                _install("OpenJS.NodeJS.LTS", log)
            npm = shutil.which("npm")
            if not npm:
                raise RuntimeError("未找到 npm，请安装 Node.js LTS 后重试。")
            log("正在安装 Codex CLI...")
            _run([npm, "install", "-g", "@openai/codex"], log)
            refresh_path()
            if os.name == "nt" and os.environ.get("APPDATA"):
                npm_directory = str(Path(os.environ["APPDATA"]) / "npm")
                os.environ["PATH"] += os.pathsep + npm_directory
        backend = shutil.which("codex")
        if not backend:
            raise FileNotFoundError("Codex 安装后仍不可用，请重启程序后重试。")
        try:
            _run([backend, "login", "status"], log, timeout=30)
        except RuntimeError:
            raise RuntimeError("Codex CLI 已安装，但登录检查未通过。请在终端运行 codex login 完成登录后重试。") from None
        log("Codex CLI 已就绪，登录状态检查通过。")

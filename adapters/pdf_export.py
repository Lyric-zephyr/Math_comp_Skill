"""Export Markdown using an installed browser and bundled offline math assets."""

import argparse
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

if __package__:
    from .tool_paths import find_tool, tool_environment
else:
    from tool_paths import find_tool, tool_environment


ASSETS = Path(__file__).resolve().parent.parent / "skills" / "Common" / "assets"
WEB_ASSETS = ASSETS / "web"


class FormulaRenderError(RuntimeError):
    def __init__(self, message, formulas):
        super().__init__(message)
        self.formulas = formulas


DOCUMENT_PARTS = re.compile(
    r"(?P<code>```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)"
    r"|(?P<math>(?<!\\)\$\$[\s\S]+?(?<!\\)\$\$|(?<!\\)\$(?!\$)(?:\\.|[^$\\])+?(?<!\\)\$(?!\$)"
    r"|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])"
)


def transform_math(content, transform):
    """只处理数学片段，保留正文、行内代码及代码块。"""
    return DOCUMENT_PARTS.sub(lambda match: match[0] if match["code"] else transform(match[0]), content)


def normalize_math_blanks(content):
    return transform_math(content, lambda text: re.sub(r"(?<!\\)_{2,}", lambda _: r"\underline{\qquad\qquad}", text))


def normalize_document(content):
    """规范排版标记与选项分段，保留公式和代码原文。"""
    protected = []

    def protect(match):
        protected.append(match[0])
        return f"\x00{len(protected) - 1}\x00"

    text = DOCUMENT_PARTS.sub(protect, normalize_math_blanks(content))
    # 居中交给模板处理，不把模型偶尔输出的 HTML 布局标签印进正文。
    text = re.sub(r"(?im)^[ \t]*<(?:div|center)\b[^>\n]*>[ \t]*", "\n", text)
    text = re.sub(r"(?im)</(?:div|center)>[ \t]*(?=\n|$)", "\n", text)
    text = re.sub(
        r"(?m)^[ \t]*(?:\*\*)?((?:第\s*[一二12]\s*[组套]\s*(?:题目|详细解析|答案与解析)|答案与解析))(?:\*\*)?[ \t]*$",
        r"## \1", text,
    )
    # 每项成为独立自然段；全角句点避免 Pandoc 把 A. 识别为字母列表。
    text = re.sub(r"(?m)^[ \t]*([A-D])(?:\\?\.|[．、)）])[ \t]*", r"\n\n\1． ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return re.sub(r"\x00(\d+)\x00", lambda match: protected[int(match[1])], text)


def find_browser():
    configured = os.environ.get("MATH_COMP_BROWSER")
    if configured:
        browser = shutil.which(configured) or (configured if Path(configured).is_file() else None)
        if not browser:
            raise FileNotFoundError("MATH_COMP_BROWSER 指定的浏览器不存在，请检查路径。")
        return browser
    for name in ("msedge", "chrome", "microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        browser = shutil.which(name)
        if browser:
            return browser
    candidates = []
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        directory = os.environ.get(variable)
        if directory:
            candidates.extend(Path(directory) / suffix for suffix in (
                "Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe",
            ))
    candidates.extend((
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    ))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError("未找到 Edge 或 Chrome。请安装其中一个浏览器后重试。")


def check_environment(engine="browser"):
    if engine == "latex":
        missing = [tool for tool in ("pandoc", "xelatex") if not find_tool(tool)]
        if missing:
            raise FileNotFoundError("LaTeX 导出缺少 " + ", ".join(missing) + "，请点击“一键配置环境”。")
        if not (ASSETS / "template.tex").is_file():
            raise FileNotFoundError("缺少 LaTeX 模板，请重新下载完整项目。")
        return find_tool("xelatex")
    if engine != "browser":
        raise ValueError(f"未知 PDF 导出方式：{engine}")
    browser = find_browser()
    required = ["document.html", "marked.umd.js", "katex.min.js", "katex.min.css"]
    css_path = WEB_ASSETS / "katex.min.css"
    if css_path.is_file():
        required.extend(re.findall(r"url\((fonts/[^)]+\.woff2)\)", css_path.read_text(encoding="utf-8")))
    missing = [name for name in required if not (WEB_ASSETS / name).is_file()]
    if missing:
        raise FileNotFoundError("离线排版资源缺失，请重新下载完整项目：" + ", ".join(missing))
    return browser


def _json(value):
    return json.dumps(value, ensure_ascii=True).replace("<", "\\u003c")


def _run_browser(command, pdf_path=None, **options):
    """浏览器临时失败时重试一次；不重试公式错误，也不重新调用 AI。"""
    for attempt in range(2):
        args = [arg + "-retry" if attempt and arg.startswith("--user-data-dir=") else arg for arg in command]
        try:
            result = subprocess.run(args, **options)
            if "--dump-dom" in args and not re.search(r'data-render-state="(?:ready|error)"', result.stdout):
                raise RuntimeError("浏览器未完成页面加载。")
            if pdf_path and (not pdf_path.is_file() or not pdf_path.read_bytes().startswith(b"%PDF-")):
                raise RuntimeError("浏览器未生成有效的 PDF。")
            return result
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, RuntimeError) as error:
            if attempt:
                details = getattr(error, "stderr", None) or str(error)
                raise RuntimeError(f"浏览器转换失败（已重试一次）：{details[-1500:]}") from error
            print("[!] 浏览器转换暂未完成，正在重试一次（不重新调用 AI）...", flush=True)


def export_pdf(md_path, title=None, engine="browser", html_only=False):
    md_path = Path(md_path).resolve()
    if not md_path.is_file():
        raise FileNotFoundError(f"找不到 Markdown 文件：{md_path}")
    source = md_path.read_text(encoding="utf-8")
    normalized = normalize_document(source)
    if normalized != source:
        md_path.write_text(normalized, encoding="utf-8")
        print("[!] 已自动规范公式与正文排版，继续导出。", flush=True)
    pdf_path = md_path.with_suffix(".pdf")
    title = title or md_path.stem
    if html_only:
        engine = "browser"
    if engine == "latex":
        check_environment(engine)
        pandoc = find_tool("pandoc")
        xelatex = find_tool("xelatex")
        subprocess.run(
            [pandoc, str(md_path), "-o", str(pdf_path), "--template", str(ASSETS / "template.tex"),
             "--lua-filter", str(ASSETS.parent / "scripts" / "format_practice.lua"),
             "--from=markdown+tex_math_single_backslash", "--metadata", f"title={title}",
             f"--pdf-engine={xelatex}", "--toc"],
            cwd=md_path.parent, check=True, timeout=180,
            env=tool_environment(pandoc, xelatex),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return pdf_path
    if engine != "browser":
        raise ValueError(f"未知 PDF 导出方式：{engine}")

    browser = check_environment()
    page = (WEB_ASSETS / "document.html").read_text(encoding="utf-8")
    page = page.replace("__ASSET_URL__", WEB_ASSETS.as_uri())
    page = page.replace("__DOCUMENT_TITLE__", _json(title))
    page = page.replace("__MARKDOWN_SOURCE__", _json(md_path.read_text(encoding="utf-8")))
    html_path = md_path.with_suffix(".html")
    html_path.write_text(page, encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix=".pdf-export-", dir=md_path.parent, ignore_cleanup_errors=True) as work:
        command = [
            browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--disable-background-networking", "--disable-component-update",
            "--allow-file-access-from-files", f"--user-data-dir={Path(work) / 'profile'}",
        ]
        options = dict(
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        # Render math and wait for local fonts before printing the resulting document.
        result = _run_browser(
            command + ["--virtual-time-budget=10000", "--dump-dom", html_path.as_uri()], **options,
        )
        rendered = result.stdout
        if not re.search(r'<html\b[^>]*data-render-state="ready"', rendered):
            error = re.search(r'<pre id="render-errors"[^>]*>(.*?)</pre>', rendered, re.S)
            details = html.unescape(error.group(1)).strip() if error else "浏览器未完成排版，请检查浏览器和离线资源。"
            data = re.search(r'<pre id="render-errors"[^>]*data-formulas="([^"]*)"', rendered)
            formulas = json.loads(html.unescape(data[1])) if data else []
            message = (
                f"公式排版失败：{details or '渲染脚本未能加载。'}\n"
                f"Markdown 和 HTML 已保留。请修正 {md_path.name} 中的公式后重新导出，无需重新调用 AI。"
            )
            if formulas:
                raise FormulaRenderError(message, formulas)
            raise RuntimeError(message)
        # Keep the fully rendered HTML so it is also useful for previewing and manual printing.
        rendered = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", rendered, flags=re.I)
        html_path.write_text(rendered, encoding="utf-8")
        if html_only:
            return html_path
        temporary_pdf = Path(work) / "document.pdf"
        _run_browser(
            command + ["--virtual-time-budget=10000", "--no-pdf-header-footer", f"--print-to-pdf={temporary_pdf}", html_path.as_uri()],
            pdf_path=temporary_pdf, **options,
        )
        if not temporary_pdf.is_file() or not temporary_pdf.read_bytes().startswith(b"%PDF-"):
            raise RuntimeError(f"浏览器没有生成 PDF。可打开 {html_path.name}，按 Ctrl+P 保存为 PDF。")
        temporary_pdf.replace(pdf_path)
    return pdf_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="将现有 Markdown 导出为 PDF，无需重新调用 AI。")
    parser.add_argument("md_path", type=Path)
    parser.add_argument("--engine", choices=("browser", "latex"), default="browser")
    args = parser.parse_args(argv)
    try:
        print(f"[+] PDF 已保存：{export_pdf(args.md_path, engine=args.engine)}")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        details = getattr(error, "stderr", None) or str(error)
        print(f"[-] PDF 导出失败：{details}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

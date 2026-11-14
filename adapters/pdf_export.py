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
    def tidy(text):
        text = re.sub(r"(?<!\\)_{2,}", lambda _: r"\underline{\qquad\qquad}", text)
        # 逗号后紧跟下一式，只留一个普通空格，不留 \quad、\qquad 大块空白。
        text = re.sub(r"([,，])\s*(?:\\q?quad\b|\\[ ;:>]|~)+\s*", lambda m: m[1] + r"\ ", text)
        if text.startswith(("$$", r"\[")):
            text = text[:2] + _normalize_formula_layout(text[2:-2]) + text[-2:]
        return text
    return transform_math(content, tidy)


FORMULA = re.compile(r"=|\\(?:lim|int|sum|prod|[dt]?frac|to|sim|equiv|approx)\b")


def _formula_boundaries(formula, separators):
    """查找括号与花括号之外的分隔符。"""
    stack, boundaries = [], []
    for token in re.finditer(r"\\(?:begin|end)\{[^{}]+\}|\\[A-Za-z]+|\\.|[{}()\[\],，;；&]", formula):
        value = token[0]
        if value.startswith(r"\begin{"):
            stack.append(value)
        elif value.startswith(r"\end{"):
            if stack and stack[-1] == value.replace(r"\end", r"\begin", 1):
                stack.pop()
        elif value in ("{", "(", "[", r"\{", r"\["):
            stack.append(value.lstrip("\\"))
        elif value in ("}", ")", "]", r"\}", r"\]"):
            if stack:
                stack.pop()
        elif not stack and value in separators:
            boundaries.append((token.start(), token.end()))
    return boundaries


def _normalize_formula_layout(formula):
    """红框外保留分隔逗号；多行公式逐行居中，不改变矩阵及分段函数内部。"""
    start, pieces = 0, []
    for box in re.finditer(r"\\boxed\s*\{", formula):
        if box.start() < start:
            continue
        depth = 1
        for token in re.finditer(r"\\.|[{}]", formula[box.end():]):
            depth += (token[0] == "{") - (token[0] == "}")
            if depth == 0:
                end = box.end() + token.start()
                inner = _normalize_formula_layout(formula[box.end():end])
                comma = re.search(r"(?<!\\)[,，](?:\s*[,，])*\s*$", inner)
                suffix = ""
                if comma:
                    inner = inner[:comma.start()].rstrip()
                    if not re.match(r"\s*[,，]", formula[end + 1:]):
                        suffix = ","
                pieces.append(formula[start:box.end()] + inner + "}" + suffix)
                start = end + 1
                break
    formula = "".join(pieces) + formula[start:]
    formula = re.sub(r"(?<!\\)[,，](?:\s*[,，])+\s*$", ",", formula)
    environment = re.fullmatch(
        r"\s*\\begin\{(aligned|split|array|gathered)\}([\s\S]*?)\\end\{\1\}\s*([,，.。]?)\s*", formula,
    )
    if not environment:
        return formula
    body = environment[2]
    if environment[1] == "array":
        columns = re.match(r"\s*\{[lcr ]+\}", body)
        if not columns:
            return formula
        body = body[columns.end():]
    boundaries = _formula_boundaries(body, {r"\\"})
    if not boundaries:
        return formula
    rows, start = [], 0
    for left, right in boundaries + [(len(body), len(body))]:
        row = body[start:left].strip()
        start = right
        spacing = re.match(r"\[[^\]\n]*\]", row) if rows else None
        if spacing:
            row = row[spacing.end():].strip()
        cells, offset = [], 0
        for begin, end in _formula_boundaries(row, {"&"}) + [(len(row), len(row))]:
            if row[offset:begin].strip():
                cells.append(row[offset:begin].strip())
            offset = end
        independent = len(cells) > 1 and all(
            FORMULA.search(cell) and not re.match(r"[=+\-<>]|\\(?:sim|equiv|approx|to|leq?|geq?|neq?)\b", cell)
            for cell in cells
        )
        rows.append((spacing[0] if spacing else "") + "\n" + ("," if independent else " ").join(cells))
    return r"\begin{gathered}" + r" \\".join(rows) + "\n" + r"\end{gathered}" + environment[3]


def _split_formula_group(formula):
    """拆开独立公式清单，保留真正的多行推导、方程组及矩阵。"""
    environment = re.fullmatch(
        r"\s*\\begin\{(aligned|array|gathered)\}([\s\S]*?)\\end\{\1\}\s*[,，.。]?\s*",
        formula,
    )
    if environment:
        body = environment[2]
        if environment[1] == "array":
            columns = re.match(r"\s*\{[lcr ]+\}", body)
            if not columns:
                return [formula]
            body = body[columns.end():]
        if re.search(r"\\(?:begin|end)\s*\{", body):
            return [formula]
        rows, start = [], 0
        for left, right in _formula_boundaries(body, {r"\\"}) + [(len(body), len(body))]:
            row = body[start:left].strip()
            start = right
            if not row:
                continue
            cells, offset = [], 0
            for begin, end in _formula_boundaries(row, {"&"}) + [(len(row), len(row))]:
                if row[offset:begin].strip():
                    cells.append(row[offset:begin].strip())
                offset = end
            row = ("," if len(cells) > 1 and all(FORMULA.search(cell) for cell in cells) else " ").join(cells)
            pieces = _split_formula_group(row)
            if not pieces or len(pieces) > 2 or any(
                not FORMULA.search(piece) or re.match(r"[=+\-<>]|\\(?:sim|equiv|approx|to|leq?|geq?|neq?)\b", piece)
                for piece in pieces
            ):
                return [formula]
            rows.append(pieces)
        if rows and any(len(row) == 2 for row in rows):
            return [piece for row in rows for piece in row]
        return [formula]
    if re.search(r"\\(?:begin|end)\s*\{", formula):
        return [formula]
    boundaries = _formula_boundaries(formula, {",", "，", ";", "；", r"\quad", r"\qquad"})
    pieces, start, separator = [], 0, ""
    for left, right in boundaries + [(len(formula), len(formula))]:
        part = re.sub(r"\A(?:\s|\\[ ,;:!>]|\\q?quad\b|~)+", "", formula[start:left]).strip()
        if not part:
            separator += formula[left:right]
            start = right
            continue
        wrapped = False
        if part.startswith(("(", "[")):
            opening, closing = ("(", ")") if part[0] == "(" else ("[", "]")
            depth = 0
            for index, character in enumerate(part):
                depth += (character == opening) - (character == closing)
                if depth == 0:
                    wrapped = index == len(part) - 1
                    break
        if FORMULA.search(part) and not wrapped and not part.startswith(("+", "-", "=", r"\pm")):
            pieces.append(part)
        elif pieces:
            pieces[-1] += separator + part
        else:
            return [formula]
        separator, start = formula[left:right], right
    return pieces if len(pieces) > 1 else [formula]


def _format_summary(text):
    """正文保留稀疏强调；易错条目转为普通编号段落，条目内可保留少量加粗词语。"""
    sections = list(re.finditer(r"(?m)^(#{2,3})[ \t]+[一二]、(知识梳理|易错总结)[^\n]*(?:\n|$)", text))
    for section in reversed(sections):
        start = section.end()
        boundary = re.search(r"(?m)^#{1," + str(len(section[1])) + r"}[ \t]+", text[start:])
        end = start + boundary.start() if boundary else len(text)
        body = text[start:end]
        if section[2] == "易错总结":
            # 只去掉包住整条标题或整段的加粗，保留条目中少量加粗的关键词。
            body = re.sub(r"(?m)^([ \t]*(?:\d+[.．、][ \t]*)?)(\*\*|__)([^\n]+?)\2(?=[ \t]*(?:[：:]|$))",
                          r"\1\3", body)
            body = re.sub(r"(?m)^([ \t]*\d+[.．、][ \t]*)(\*\*|__)([^\n*_]+?[：:])\2", r"\1\3", body)
            number = 0

            def plain_item(match):
                nonlocal number
                number += 1
                title = re.sub(r"^\d+[.．、][ \t]*", "", match[1].strip())
                return f"{number}.{title}" + ("" if re.search(r"[：:]", title) else "：")

            body = re.sub(r"(?m)^#{3,6}[ \t]+([^\n]+)", plain_item, body)
            body = re.sub(r"(?m)^[ \t]*(\d+)[.．、][ \t]*", r"\n\n\1.", body)
            body = re.sub(r"(?m)^(\d+\.[^\n：:]+[：:])[ \t]*\n+[ \t]*", r"\1", body)
            body = "\n" + re.sub(r"\n{3,}", "\n\n", body).strip() + "\n\n"
        else:
            def emphasize(topic):
                prose = re.sub(r"(?m)^#{1,6}[ \t]+[^\n]*", "", topic)
                if re.search(r"\*\*[^*\n]+\*\*|__[^_\n]+__", prose):
                    return topic
                keywords = r"充要条件|必要条件|充分条件|当且仅当|适用条件|收敛条件|定义域|存在条件|一致连续|绝对收敛|一致收敛|解析函数|单调有界|左右极限|收敛半径|唯一性|留数|极限|收敛|连续|导数|积分|变换|级数"
                for match in re.finditer(keywords, topic):
                    line = topic[topic.rfind("\n", 0, match.start()) + 1:match.start()]
                    if not line.lstrip().startswith(("#", ">", "|", "- ", "+ ")):
                        return topic[:match.start()] + "**" + match[0] + "**" + topic[match.end():]
                return topic

            body = "".join(emphasize(topic) for topic in re.split(
                r"(?m)(?=^#{" + str(len(section[1]) + 1) + r"}[ \t]+)", body,
            ))
        text = text[:start] + body + text[end:]
    return text


def normalize_document(content):
    """规范排版标记与选项分段，保留公式和代码原文。"""
    protected = []

    def protect(match):
        protected.append(match[0])
        return f"\x00{len(protected) - 1}\x00"

    text = DOCUMENT_PARTS.sub(protect, normalize_math_blanks(content))
    # 并列公式先独立成段；只有变量或代码的枚举仍保留行内排版。
    atom = r"\x00\d+\x00"
    separator = r"[ \t]*(?:[,，、;；][ \t]*(?:(?:以及|及|和)[ \t]*)?|(?:以及|及|和)[ \t]*)"

    def split_group(match):
        value = protected[int(match[1])]
        part = DOCUMENT_PARTS.fullmatch(value)
        line = text[text.rfind("\n", 0, match.start()) + 1:match.start()]
        if not part or not part["math"] or line.lstrip().startswith(("#", "|", ">")):
            return match[0]
        width = 2 if value.startswith(("$$", r"\(", r"\[")) else 1
        pieces = _split_formula_group(value[width:-width])
        if len(pieces) < 2:
            return match[0]
        tokens = []
        for piece in pieces:
            tokens.append(f"\x00{len(protected)}\x00")
            protected.append("$$\n" + _normalize_formula_layout(piece) + "\n$$")
        return "\n\n" + "\n\n".join(tokens) + "\n\n"

    text = re.sub(r"\x00(\d+)\x00[ \t]*[，,。；;]?", split_group, text)

    def display_group(match):
        indexes = [int(number) for number in re.findall(r"\x00(\d+)\x00", match[0])]
        parts = [DOCUMENT_PARTS.fullmatch(protected[index]) for index in indexes]
        line = text[text.rfind("\n", 0, match.start()) + 1:match.start()]
        if line.lstrip().startswith(("#", "|", ">")) or not all(part and part["math"] for part in parts):
            return match[0]
        formulas = [part[0][2:-2] if part[0].startswith(("$$", r"\(", r"\[")) else part[0][1:-1] for part in parts]
        if sum(bool(FORMULA.search(formula)) for formula in formulas) < 2:
            return match[0]
        for index, formula in zip(indexes, formulas):
            protected[index] = "$$\n" + _normalize_formula_layout(formula.strip()) + "\n$$"
        return "\n\n" + "\n\n".join(f"\x00{index}\x00" for index in indexes) + "\n\n"

    text = re.sub(atom + "(?:" + separator + atom + ")+[ \t]*[，,。；;]?", display_group, text)
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
    # 中文句末标点留在粗体外，避免 **重点。**下一句 被 Markdown 当成普通文字。
    text = re.sub(r"\*\*([^*\n]*[^\s*，。；：！？、,.!?;:])([，。；：！？、,.!?;:]+)\*\*", r"**\1**\2", text)
    text = _format_summary(text)
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

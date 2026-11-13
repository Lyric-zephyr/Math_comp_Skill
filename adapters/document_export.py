"""Save one selected document format using the shared rendering tools."""

import base64
from contextlib import contextmanager
from itertools import count
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

if __package__:
    from .pdf_export import WEB_ASSETS, FormulaRenderError, check_environment, export_pdf, normalize_document
    from .tool_paths import find_tool, tool_environment
else:
    from pdf_export import WEB_ASSETS, FormulaRenderError, check_environment, export_pdf, normalize_document
    from tool_paths import find_tool, tool_environment


OUTPUT_FORMATS = {"Word": "word", "PDF": "pdf", "MD": "md", "HTML": "html"}
PRACTICE_HEADING = r"(?:第\s*[12一二]\s*[组套]|(?:参考)?答案|详细解析)"


def add_output_arguments(parser):
    parser.add_argument("--output-format", choices=tuple(OUTPUT_FORMATS.values()), default="pdf")


def check_output_environment(output_format="pdf", pdf_engine="browser"):
    if output_format not in OUTPUT_FORMATS.values():
        raise ValueError(f"未知输出格式：{output_format}")
    if output_format == "md":
        return None
    if output_format == "word":
        pandoc = find_tool("pandoc")
        if not pandoc:
            raise FileNotFoundError("Word 导出需要 Pandoc，请点击“一键配置环境”。")
        return pandoc
    return check_environment("browser" if output_format == "html" else pdf_engine)


def _standalone_html(path):
    """Embed the offline stylesheet and fonts in the selected HTML artifact."""
    css = (WEB_ASSETS / "katex.min.css").read_text(encoding="utf-8")

    def embed_font(match):
        font = WEB_ASSETS / match[1]
        data = base64.b64encode(font.read_bytes()).decode("ascii")
        return f"url(data:font/woff2;base64,{data})"

    css = re.sub(r"url\((fonts/[^)]+\.woff2)\)", embed_font, css)
    page = path.read_text(encoding="utf-8")
    page = re.sub(r'<link\b[^>]*href="[^"]*/katex\.min\.css"[^>]*>', lambda _: f"<style>{css}</style>", page)
    path.write_text(page, encoding="utf-8")


def _format_word(path, practice):
    """Apply the existing Chinese typography rules to Pandoc's Word styles."""
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    tag = lambda name: f"{{{namespace}}}{name}"

    def element(parent, name):
        child = parent.find(tag(name))
        return child if child is not None else ET.SubElement(parent, tag(name))

    with zipfile.ZipFile(path) as archive:
        styles = ET.fromstring(archive.read("word/styles.xml"))
        document = ET.fromstring(archive.read("word/document.xml"))
        for style in styles.findall(tag("style")):
            name = style.get(tag("styleId"))
            if name not in ("Normal", "BodyText", "FirstParagraph", "Compact", "Title", "Heading1", "Heading2", "Heading3", "Heading4", "Heading5"):
                continue
            heading = name == "Title" or name.startswith("Heading")
            size = 36 if name in ("Title", "Heading1") else 32 if name == "Heading2" else 28
            properties = element(style, "rPr")
            fonts = element(properties, "rFonts")
            for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
                fonts.set(tag(attribute), "SimHei" if heading else "SimSun")
            for attribute in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
                fonts.attrib.pop(tag(attribute), None)
            element(properties, "sz").set(tag("val"), str(size))
            element(properties, "szCs").set(tag("val"), str(size))
            if heading:
                element(properties, "b").set(tag("val"), "1")
            paragraph = element(style, "pPr")
            element(paragraph, "ind").set(tag("firstLine"), "0" if heading or name == "Compact" else "560")
            element(paragraph, "spacing").set(tag("line"), "408")
            element(paragraph, "spacing").set(tag("lineRule"), "auto")
            if heading:
                alignment = "center" if name in ("Title", "Heading1") or name == "Heading2" and practice else "left"
                element(paragraph, "jc").set(tag("val"), alignment)
            # Word style properties precede run properties in the XML schema.
            style.remove(paragraph)
            style.insert(list(style).index(properties), paragraph)
        for paragraph in document.iter(tag("p")):
            text = "".join(item.text or "" for item in paragraph.iter(tag("t"))).strip()
            display_math = not text and paragraph.find("{http://schemas.openxmlformats.org/officeDocument/2006/math}oMathPara") is not None
            if display_math or re.fullmatch(r"【难度[：:].+】", text):
                properties = element(paragraph, "pPr")
                element(properties, "ind").set(tag("firstLine"), "0")
                element(properties, "jc").set(tag("val"), "center" if display_math else "left")
                paragraph.remove(properties)
                paragraph.insert(0, properties)
        for run in document.iter(tag("r")):
            properties = run.find(tag("rPr"))
            bold = None if properties is None else properties.find(tag("b"))
            if bold is not None and bold.get(tag("val"), "1") not in ("0", "false", "off"):
                fonts = element(properties, "rFonts")
                for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
                    fonts.set(tag(attribute), "SimHei")
                for attribute in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
                    fonts.attrib.pop(tag(attribute), None)
                properties.remove(fonts)
                properties.insert(1 if properties.find(tag("rStyle")) is not None else 0, fonts)
                element(properties, "bCs").set(tag("val"), "1")
        replacements = {"word/styles.xml": ET.tostring(styles, encoding="utf-8", xml_declaration=True),
                        "word/document.xml": ET.tostring(document, encoding="utf-8", xml_declaration=True)}
        formatted = path.with_name("formatted.docx")
        with zipfile.ZipFile(formatted, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for item in archive.infolist():
                output.writestr(item, replacements[item.filename] if item.filename in replacements else archive.read(item.filename))
    formatted.replace(path)


@contextmanager
def _unused_prefix(filename_prefix):
    """Reserve a document name across formats and concurrent export processes."""
    original = Path(filename_prefix).expanduser().resolve()
    original.parent.mkdir(parents=True, exist_ok=True)
    for number in count(1):
        prefix = original if number == 1 else original.with_name(f"{original.name}_{number}")
        reservation = prefix.with_name(f".{prefix.name}.export-lock")
        try:
            reservation.mkdir()
        except FileExistsError:
            continue
        try:
            if any(Path(f"{prefix}.{extension}").exists() for extension in ("md", "pdf", "html", "docx")):
                continue
            yield prefix
            return
        finally:
            reservation.rmdir()


def save_document(content, filename_prefix, output_format="pdf", pdf_engine="browser", repair=None):
    with _unused_prefix(filename_prefix) as prefix:
        return _save_document(content, prefix, output_format, pdf_engine, repair)


def _save_document(content, filename_prefix, output_format="pdf", pdf_engine="browser", repair=None):
    check_output_environment(output_format, pdf_engine)
    normalized = normalize_document(content)
    if normalized != content:
        print("[!] 已自动规范公式与正文排版，继续导出。", flush=True)
    content = normalized
    prefix = Path(filename_prefix).expanduser().resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    extension = "docx" if output_format == "word" else output_format
    destination = Path(f"{prefix}.{extension}")
    if output_format == "md":
        destination.write_text(content.rstrip() + "\n", encoding="utf-8")
        return destination
    try:
        for attempt in range(3):
            try:
                with tempfile.TemporaryDirectory(prefix=".document-export-", dir=prefix.parent, ignore_cleanup_errors=True) as work:
                    source = Path(work) / "document.md"
                    source.write_text(content.rstrip() + "\n", encoding="utf-8")
                    if output_format == "word":
                        pandoc = find_tool("pandoc")
                        result = source.with_suffix(".docx")
                        subprocess.run(
                            [pandoc, str(source), "-o", str(result), "--from=markdown+tex_math_single_backslash",
                             "--metadata", f"title={prefix.name}", "--toc", "--toc-depth=2"],
                            check=True, timeout=180, env=tool_environment(pandoc), capture_output=True,
                            text=True, encoding="utf-8", errors="replace",
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                        )
                        _format_word(result, bool(re.search(r"(?m)^##[ \t]+" + PRACTICE_HEADING, content)))
                    else:
                        result = export_pdf(source, title=prefix.name, engine=pdf_engine, html_only=output_format == "html")
                        if output_format == "html":
                            _standalone_html(result)
                    result.replace(destination)
                break
            except FormulaRenderError as error:
                if repair is None or attempt == 2:
                    raise
                print(f"[!] 公式排版失败，正在自动修复并重试 [{attempt + 1}/2]（仅修复报错公式，不重新生成正文）...", flush=True)
                try:
                    updated = normalize_document(repair(content, error))
                except (ValueError, RuntimeError, subprocess.TimeoutExpired):
                    if attempt == 1:
                        raise
                    print("[!] 本次公式修复未完成，将再试一次。", flush=True)
                    continue
                if updated == content:
                    print("[!] 修复未改变报错公式，继续尝试。", flush=True)
                content = updated
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        recovery = Path(f"{prefix}.md")
        recovery.write_text(content.rstrip() + "\n", encoding="utf-8")
        print("[ARTIFACT] " + json.dumps({"path": str(recovery), "kind": "recovery"}, ensure_ascii=False), flush=True)
        print(f"[!] 格式转换未完成，Markdown 已保留：{recovery}，无需重新调用 AI。", flush=True)
        if isinstance(error, PermissionError):
            raise RuntimeError("无法写入输出文档，请关闭正在打开的同名文件，并检查输出目录权限后重试导出。") from error
        if isinstance(error, subprocess.TimeoutExpired):
            raise RuntimeError("格式转换超时，Markdown 已保留，可重新导出，无需重新生成。") from error
        if isinstance(error, subprocess.CalledProcessError):
            details = error.stderr or error.stdout or str(error)
            raise RuntimeError(f"格式转换程序失败（退出码 {error.returncode}）：{details[-1500:]}") from error
        if isinstance(error, RuntimeError):
            message = str(error).replace("Markdown 和 HTML 已保留。", "Markdown 已保留。")
            raise RuntimeError(message.replace("document.md", recovery.name)) from error
        raise
    return destination

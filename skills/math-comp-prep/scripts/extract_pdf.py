"""提取用户提供的 PDF 文字；扫描页使用 Windows OCR，识别结果仅供本次运行使用。"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def extract_text(pdf_path, log=None):
    import pymupdf as fitz

    log = log or (lambda message: print(message, file=sys.stderr, flush=True))
    pdf_path = Path(pdf_path).resolve()
    with fitz.open(pdf_path) as document:
        if document.needs_pass:
            raise ValueError("PDF 已加密，请先解密再提取。")
        if not document.permissions & fitz.PDF_PERM_COPY:
            raise ValueError("PDF 限制复制，停止自动提取；请使用有权提取的教材。")
        texts = [page.get_text() for page in document]
        scanned = [number for number, text in enumerate(texts)
                   if not text.strip() and (document[number].get_images() or document[number].get_drawings())]
        if not scanned:
            return "\n".join(texts)

        powershell = shutil.which("powershell") if os.name == "nt" else None
        if not powershell:
            raise RuntimeError("扫描教材自动 OCR 需要 Windows PowerShell；请先为 PDF 添加文字层后重试。")
        log(f"检测到 {len(scanned)} 个无文字层页面，开始本地 OCR；识别结果仅用于本次运行。")
        script = Path(__file__).with_name("ocr_windows.ps1")
        for start in range(0, len(scanned), 16):
            batch = scanned[start:start + 16]
            with tempfile.TemporaryDirectory(prefix="math-comp-ocr-") as directory:
                for number in batch:
                    document[number].get_pixmap(dpi=180).save(Path(directory) / f"{number + 1:05d}.png")
                try:
                    result = subprocess.run(
                        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                         str(script), "-ImageDirectory", directory],
                        capture_output=True, text=True, encoding="utf-8-sig", errors="replace",
                        timeout=180, creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                except subprocess.TimeoutExpired:
                    raise RuntimeError("本批教材 OCR 超时，请重试；本次识别结果未保存。") from None
            if result.returncode:
                details = result.stderr.strip() or "请检查 Windows 中文 OCR 语言包。"
                raise RuntimeError(f"教材 OCR 失败：{details}")
            records = json.loads(result.stdout)
            if not isinstance(records, list):
                raise ValueError("教材 OCR 返回格式异常，请重试。")
            recognized = {str(item["page"]): item["text"] for item in records
                          if isinstance(item, dict) and isinstance(item.get("text"), str) and "page" in item}
            if any(str(number + 1) not in recognized for number in batch):
                raise ValueError("教材 OCR 返回缺少页面，请重试。")
            for number in batch:
                texts[number] = re.sub(r"(?<=[\u3400-\u9fff])[ \t]+(?=[\u3400-\u9fff])", "", recognized[str(number + 1)])
            log(f"教材 OCR 进度：{start + len(batch)}/{len(scanned)} 页。")
        log("教材 OCR 完成；生成时将要求 AI 结合上下文校正文字与公式，无法确认的内容会标注或跳过。")
        return "\n".join(texts)


def main(argv=None):
    parser = argparse.ArgumentParser(description="提取用户提供的 PDF 文本；扫描页自动使用 Windows OCR，不缓存识别结果。")
    parser.add_argument("pdf_path", type=Path, help="教材 PDF 路径")
    parser.add_argument("--output", "-o", type=Path, help="保存为 UTF-8 文本；默认输出到终端")
    args = parser.parse_args(argv)
    try:
        text = extract_text(args.pdf_path)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
            print(f"文本已保存: {args.output.resolve()}")
        else:
            print(text, end="")
    except ImportError:
        print("提取失败: 请先运行 python -m pip install PyMuPDF", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"提取失败: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

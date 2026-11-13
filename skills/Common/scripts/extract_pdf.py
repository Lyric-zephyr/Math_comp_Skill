"""提取任意教材 PDF；扫描页使用 Windows OCR，未变化的教材复用本地识别缓存。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from adapters.task_progress import report_progress


CACHE_DIR = Path(__file__).resolve().parents[3] / "local_textbook" / ".ocr-cache"


def _file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _save_cache(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            json.dump(data, output, ensure_ascii=False)
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def extract_text(pdf_path, log=None, use_cache=True, refresh=False, cache_dir=None):
    import pymupdf as fitz

    log = log or (lambda message: print(message, file=sys.stderr, flush=True))
    pdf_path = Path(pdf_path).resolve()
    report_progress(0, "检查教材及识别缓存", log)
    with fitz.open(pdf_path) as document:
        if document.needs_pass:
            raise ValueError("PDF 已加密，请先解密再提取。")
        if not document.permissions & fitz.PDF_PERM_COPY:
            raise ValueError("PDF 限制复制，停止自动提取；请使用有权提取的教材。")
        # 以文件内容及提取流程为依据；改名可复用，同名内容变化不能误用旧结果。
        source_digest = _file_digest(pdf_path) if use_cache else None
        pipeline = hashlib.sha256((
            _file_digest(Path(__file__)) + _file_digest(Path(__file__).with_name("ocr_windows.ps1"))
            + fitz.VersionBind + os.name
        ).encode("utf-8")).hexdigest() if use_cache else None
        cache = Path(cache_dir or CACHE_DIR) / f"{source_digest}.json"
        if use_cache and not refresh and cache.is_file():
            try:
                saved = json.loads(cache.read_text(encoding="utf-8"))
                if (not isinstance(saved, dict) or saved.get("version") != 1
                        or saved.get("source_sha256") != source_digest or saved.get("pipeline") != pipeline
                        or saved.get("pages") != len(document) or not isinstance(saved.get("text"), str)
                        or not saved["text"].strip()
                        or saved.get("text_sha256") != hashlib.sha256(saved["text"].encode("utf-8")).hexdigest()):
                    raise ValueError("缓存过期或内容不完整")
                log(f"复用教材识别缓存：{pdf_path.name}，跳过文字提取和 OCR。")
                report_progress(100, "已复用教材缓存", log)
                return saved["text"]
            except (OSError, ValueError):
                log(f"教材缓存失效或损坏，重新识别：{pdf_path.name}")
        texts = []
        for number, page in enumerate(document):
            texts.append(page.get_text())
            if (number + 1) % 16 == 0 or number + 1 == len(document):
                report_progress(25 * (number + 1) / len(document), f"检查文字层 {number + 1}/{len(document)} 页", log)
        scanned = [number for number, text in enumerate(texts)
                   if not text.strip() and (document[number].get_images() or document[number].get_drawings())]
        powershell = shutil.which("powershell") if os.name == "nt" else None
        if scanned and not powershell:
            raise RuntimeError("扫描教材自动 OCR 需要 Windows PowerShell；请先为 PDF 添加文字层后重试。")
        if scanned:
            log(f"检测到 {len(scanned)} 个无文字层页面，开始本地 OCR；成功后保存识别缓存。")
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
                    raise RuntimeError("本批教材 OCR 超时，请重试；未完成的识别不会写入缓存。") from None
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
            report_progress(25 + 70 * (start + len(batch)) / len(scanned), "正在识别扫描教材", log)
        if scanned:
            log("教材 OCR 完成；生成时将要求 AI 结合上下文校正文字与公式，无法确认的内容会标注或跳过。")
        text = "\n".join(texts)
        if use_cache and text.strip():
            if _file_digest(pdf_path) != source_digest:
                raise RuntimeError("教材在识别过程中发生变化，请重试；未保存本次识别缓存。")
            report_progress(95, "保存教材识别缓存", log)
            try:
                _save_cache(cache, {"version": 1, "source_sha256": source_digest, "pipeline": pipeline,
                                    "pages": len(document), "text": text,
                                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
                log(f"教材识别缓存已保存：{cache}")
            except OSError as error:
                log(f"无法保存教材缓存，本次仍可使用识别结果：{error}")
        report_progress(100, "教材读取完成", log)
        return text


def main(argv=None):
    parser = argparse.ArgumentParser(description="提取任意教材 PDF 文本；扫描页自动 OCR，未变化的教材复用本地缓存。")
    parser.add_argument("pdf_path", type=Path, help="教材 PDF 路径")
    parser.add_argument("--output", "-o", type=Path, help="保存为 UTF-8 文本；默认输出到终端")
    parser.add_argument("--refresh", action="store_true", help="忽略已有教材缓存，重新提取及 OCR 并更新缓存")
    parser.add_argument("--no-cache", action="store_true", help="本次既不读取也不保存教材识别缓存")
    args = parser.parse_args(argv)
    try:
        text = extract_text(args.pdf_path, use_cache=not args.no_cache, refresh=args.refresh)
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

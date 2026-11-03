"""用 PyMuPDF 提取教材中可选中的文字；扫描件的 OCR 由其他脚本处理。"""

import argparse
from pathlib import Path
import sys


def extract_text(pdf_path):
    import fitz

    with fitz.open(pdf_path) as document:
        if document.needs_pass:
            raise ValueError("PDF 已加密，请先解密再提取。")
        return "\n".join(page.get_text() for page in document)


def main(argv=None):
    parser = argparse.ArgumentParser(description="提取教材 PDF 的文本（不含 OCR）。")
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

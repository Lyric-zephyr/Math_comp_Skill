"""使用 XeLaTeX 编译独立的中文 LaTeX 文档。"""

import argparse
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from adapters.tool_paths import find_tool, tool_environment


def compile_latex(tex_path):
    tex_path = Path(tex_path).expanduser().resolve()
    if not tex_path.is_file():
        raise FileNotFoundError(f"找不到 LaTeX 文件: {tex_path}")
    engine = find_tool("xelatex")
    if not engine:
        raise FileNotFoundError("找不到 xelatex，请安装 TeX Live 或 MiKTeX 并配置 PATH。")

    for pass_number in range(1, 3):
        print(f"[*] XeLaTeX 编译 [{pass_number}/2]: {tex_path.name}", flush=True)
        subprocess.run(
            [engine, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=tex_path.parent,
            env=tool_environment(engine),
            check=True,
        )

    pdf_path = tex_path.with_suffix(".pdf")
    if not pdf_path.is_file():
        raise FileNotFoundError(f"编译结束但没有生成 PDF: {pdf_path}")
    return pdf_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="使用 XeLaTeX 编译独立 .tex 文档（两遍）。")
    parser.add_argument("tex_path", type=Path, help="独立 LaTeX 文件路径，不是 Pandoc 模板")
    args = parser.parse_args(argv)
    try:
        pdf_path = compile_latex(args.tex_path)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"[-] 编译失败: {error}", file=sys.stderr)
        return 1
    print(f"[+] 编译成功，PDF 已保存: {pdf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

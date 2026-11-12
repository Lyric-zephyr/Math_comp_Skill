"""Generate study content with Doubao API and save the selected format."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

if __package__:
    from .document_export import add_output_arguments, check_output_environment, save_document
    from .ai_runtime import add_runtime_arguments, generate_content, save_generated_document
    from .skill_rules import order_problem_set, validate_problem_set
else:
    from document_export import add_output_arguments, check_output_environment, save_document
    from ai_runtime import add_runtime_arguments, generate_content, save_generated_document
    from skill_rules import order_problem_set, validate_problem_set


BASE_DIR = Path(__file__).resolve().parent.parent


def open_document(document_path):
    """Open the selected output without treating viewer errors as failures."""
    try:
        if os.name == "nt":
            os.startfile(str(document_path))
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.run([opener, str(document_path)], check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"[!] 文件已生成，但无法自动打开: {error}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="通过豆包 API 生成 Word、PDF、MD 或 HTML。")
    parser.add_argument("prompt", nargs="?", default="测试Prompt", help="发送给 AI 的提示词")
    parser.add_argument("filename_prefix", nargs="?", default="output", help="输出文件前缀（不含扩展名）")
    parser.add_argument("--pdf-engine", choices=("browser", "latex"), default="browser")
    add_output_arguments(parser)
    add_runtime_arguments(parser, "doubao")
    args = parser.parse_args(argv)

    try:
        check_output_environment(args.output_format, args.pdf_engine)

        print(f"[*] 正在通过豆包生成: {args.filename_prefix}", flush=True)
        content = order_problem_set(generate_content("doubao", args, BASE_DIR))
        if not content:
            raise ValueError("AI 返回了空内容，未生成文档。")
        if args.task_mode == "practice" or "任务：【练习】" in args.prompt:
            try:
                validate_problem_set(content)
            except ValueError:
                recovery = save_document(content, args.filename_prefix, "md")
                print("[ARTIFACT] " + json.dumps({"path": str(recovery), "kind": "recovery"}, ensure_ascii=False), flush=True)
                print(f"[!] 练习结构不符合要求，原文已保留：{recovery}", flush=True)
                raise

        print(f"[*] 正在导出 {args.output_format.upper()}...", flush=True)
        document_file = save_generated_document("doubao", args, BASE_DIR, content)
    except subprocess.CalledProcessError as error:
        details = error.stderr or error.stdout or str(error)
        print(f"[-] 生成失败: {details.strip()}", file=sys.stderr, flush=True)
        return 1
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"[-] 生成失败: {error}", file=sys.stderr, flush=True)
        return 1

    print("[ARTIFACT] " + json.dumps({"path": str(document_file), "kind": "document"}, ensure_ascii=False), flush=True)
    print(f"[+] 文件已保存: {document_file}", flush=True)
    open_document(document_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())

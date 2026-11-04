"""检查练习是否与同模块历史重复；可显式登记已有 Markdown 练习。"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from adapters.practice_history import (find_duplicates, history_file, load_history,
                                      question_blocks, save_history)
from adapters.skill_rules import MODULE_RULES, order_problem_set, validate_problem_set


def main(argv=None):
    parser = argparse.ArgumentParser(description="按模块检查练习重复；只记录题干，不保存教材识别结果。")
    parser.add_argument("markdown", nargs="?", type=Path, help="待检查的 Markdown 练习；不填时显示历史题数")
    parser.add_argument("--chapter", choices=tuple(MODULE_RULES), required=True)
    parser.add_argument("--record", action="store_true", help="检查通过后登记为已出题目，用于导入以前的练习")
    args = parser.parse_args(argv)
    if args.record and args.markdown is None:
        parser.error("--record 需要提供 Markdown 文件。")
    try:
        with history_file(args.chapter) as path:
            previous = load_history(path, args.chapter)
            if args.markdown is None:
                print(f"{args.chapter}：已记录 {len(previous)} 道题。历史文件：{path}")
                return 0
            content = order_problem_set(args.markdown.read_text(encoding="utf-8-sig"))
            validate_problem_set(content)
            questions = question_blocks(content)
            duplicates = find_duplicates(questions, previous)
            if duplicates:
                raise ValueError("\n".join(duplicates))
            if args.record:
                save_history(path, args.chapter, previous + [text for _, text in questions])
            print("检查通过：20 题无检测到的重复。" + ("已登记练习历史。" if args.record else "历史未更新。"))
    except (OSError, ValueError, RuntimeError) as error:
        print(f"检查失败：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

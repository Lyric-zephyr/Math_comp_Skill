"""One set of skill rules and document ordering for every AI adapter."""

from pathlib import Path
import re


SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "math-comp-prep"
MODULE_RULES = {
    "模块一：极限与连续": ("01_limit.md", ("极限", "连续", "间断点")),
    "模块二：一元微分学": ("02_diff1.md", ("导数", "微分", "中值定理")),
    "模块三：一元积分学": ("03_int1.md", ("不定积分", "定积分", "积分应用")),
    "模块四：多元微分学": ("04_diffn.md", ("偏导", "全微分", "多元极值")),
    "模块五：多元积分学": ("05_intn.md", ("重积分", "曲线积分", "曲面积分")),
    "模块六：级数与方程": ("06_series.md", ("级数", "微分方程")),
    "模块七：综合全实战": ("07_comprehensive.md", ("极限", "导数", "积分", "级数", "微分方程")),
}


def build_prompt(mode, chapter, context, log=print):
    if mode not in ("总结知识点", "练习"):
        raise ValueError(f"未知任务模式：{mode}")
    general_rule = "knowledge_summary.md" if mode == "总结知识点" else "problem_set.md"
    entry = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    # The entrypoint documents both tasks; send only shared and selected rules
    # to the AI so practice requirements cannot become summary instructions.
    common, sections = entry.split("## 总结模式", 1)
    summary_rules, practice_rules = sections.split("## 练习模式", 1)
    selected = "## 总结模式" + summary_rules if mode == "总结知识点" else "## 练习模式" + practice_rules
    paths = [SKILL_DIR / "references" / general_rule,
             SKILL_DIR / "references" / "modules" / MODULE_RULES[chapter][0]]
    rules = "\n\n".join([common, selected] + [path.read_text(encoding="utf-8") for path in paths])
    task_instruction = ("本任务只整理知识点、公式、定理及适用条件；输出结构严格遵守知识点总结规则。"
                        "教材为可选参考：有相关内容时优先参考，缺失或不足时依据自身的高等数学知识直接生成完整总结，"
                        "不得因未提供教材而拒绝生成或要求补充资料，不编造教材出处。")
    if mode == "总结知识点" and not context.strip():
        context = "本次未提供相关教材，请依据自身的高等数学知识生成当前模块的完整总结。"
    if mode == "练习":
        if __package__:
            from .problem_sources import load_practice_sources
        else:
            from problem_sources import load_practice_sources
        log("正在读取非数 A 为主的真题参考及开放题库；扫描件首次读取可能需要 OCR。")
        context = load_practice_sources(chapter, MODULE_RULES[chapter][1], log=log) + "\n\n【用户教材片段】\n" + context[:6000]
        task_instruction = ("练习按非数学A类训练：两套各5道填空、5道解答，每套题号1-10；"
                            "先列完两套题目，再集中写答案与解析，并先居中标明第一套或第二套。")
    return (
        f"请使用 math-comp-prep 技能。任务：【{mode}】，章节：【{chapter}】。"
        "遵守下方已附的技能规则，只返回该章节的 Markdown 正文，"
        "不要用代码块包裹全文；文件保存、格式转换和排版由启动器完成。"
        r"公式使用 KaTeX 支持的语法；分式必须完整写成 \frac{分子}{分母}，"
        r"例如 \frac{0}{0}、\frac{\infty}{\infty}，不得省略分子、分母或花括号。"
        r"数学环境内的填空横线写成 \underline{\qquad\qquad}，不得使用连续下划线。"
        "输出前检查每个公式的参数、花括号及数学定界符是否完整配对。"
        f"{task_instruction}\n\n"
        f"【技能规则】\n{rules}\n\n【参考资料】\n{context}"
    )


def order_problem_set(content):
    """Keep both papers first and restart numbering in each paper and solution."""
    sections = list(re.finditer(r"^##[ \t]+第[ \t]*([12一二])[ \t]*[组套][ \t]*(题目|详细解析|答案与解析)[^\n]*$", content, re.M))
    keys = [("详细解析" if match[2] != "题目" else "题目", "1" if match[1] in ("1", "一") else "2") for match in sections]
    expected = [("题目", "1"), ("题目", "2"), ("详细解析", "1"), ("详细解析", "2")]
    if len(keys) != 4 or set(keys) != set(expected):
        return content
    blocks = {}
    for index, match in enumerate(sections):
        body = content[match.end():sections[index + 1].start() if index + 1 < len(sections) else len(content)]
        body = re.sub(r"(?m)^##[ \t]+答案与解析[^\n]*\n?", "", body)
        number = 0

        def renumber(question):
            nonlocal number
            number += 1
            return f"{question[1]} 第 {number} 题"

        body = re.sub(r"(?m)^(#{3,4})[ \t]+第[ \t]*\d+[ \t]*题", renumber, body)
        kind, paper = keys[index]
        blocks[keys[index]] = f"## 第{'一' if paper == '1' else '二'}套 {kind}\n\n{body.strip()}"
    prefix = content[:sections[0].start()].rstrip()
    ordered = [blocks[key] for key in expected[:2]] + ["## 答案与解析"] + [blocks[key] for key in expected[2:]]
    return "\n\n".join(([prefix] if prefix else []) + ordered) + "\n"


def validate_problem_set(content):
    """Check the paper structure without pretending to judge mathematical depth."""
    for paper in ("第一套", "第二套"):
        for kind in ("题目", "详细解析"):
            match = re.search(r"(?ms)^##[ \t]+" + paper + " " + kind + r"\s*\n(.*?)(?=^##[ \t]+|\Z)", content)
            if match is None:
                raise ValueError(f"练习结构不完整：缺少{paper}{kind}。")
            body = match[1]
            numbers = re.findall(r"(?m)^#{3,4}[ \t]+第[ \t]*(\d+)[ \t]*题", body)
            if numbers != [str(number) for number in range(1, 11)]:
                raise ValueError(f"{paper}{kind}必须独立包含第 1-10 题。")
            if kind == "题目":
                for label, expected in (("一、填空题", list(range(1, 6))), ("二、解答题", list(range(6, 11)))):
                    section = re.search(r"(?ms)^###[ \t]+" + label + r"\s*\n(.*?)(?=^###[ \t]+|\Z)", body)
                    actual = [] if section is None else [int(number) for number in re.findall(r"(?m)^####[ \t]+第[ \t]*(\d+)[ \t]*题", section[1])]
                    if actual != expected:
                        raise ValueError(f"{paper}须包含 5 道填空题（1-5）和 5 道解答题（6-10）。")

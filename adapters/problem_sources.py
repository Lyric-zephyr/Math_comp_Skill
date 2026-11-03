"""Provide traceable official references and bundled open practice material."""

import importlib.util
from functools import lru_cache
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def source_reader():
    script = ROOT / "skills" / "math-comp-prep" / "scripts" / "scrape_cmathc.py"
    spec = importlib.util.spec_from_file_location("scrape_cmathc", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def open_source_index(log=print):
    module = source_reader()
    module.collect(log=log)
    return module.CACHE / "source_index.html"


def load_practice_sources(chapter, keywords, log=print):
    module = source_reader()
    official = []
    try:
        official = module.excerpts(keywords, log=log)
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        log(f"真题参考未完成：{error}")
    # Give non-mathematics A most of the source budget; the other categories
    # are supplementary and must still pass the selected module's boundaries.
    parts = []
    remaining = 7500
    for item in official:
        if remaining <= 0:
            break
        excerpt = item[:min(2600, remaining)]
        parts.append(excerpt)
        remaining -= len(excerpt)
    bank = ROOT / "skills" / "math-comp-prep" / "assets" / "open_problems"
    for path in sorted(bank.glob("*.json")):
        for item in json.loads(path.read_text(encoding="utf-8"))["problems"]:
            if chapter not in item["modules"] and "综合" not in chapter:
                continue
            parts.append(f"【开放练习参考，非全国竞赛真题】{item['id']}\n{item['problem']}\n"
                         f"来源：{item['source']}\n许可：{item['license']}\n署名：{item['attribution']}\n改动：{item['changes']}")
            if sum(map(len, parts)) > 11000:
                break
    status = "已提供实际在线读取的真题文本；只可据此标注来源，不得编造届次或题号。" if official else "未核验真题参考：本次没有取得可用的真题正文，只能标为模拟训练。"
    log(status)
    return status + "\n\n" + "\n\n".join(parts)

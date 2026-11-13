"""Provide official references and open material hosted in Assistant_course."""

import importlib.util
from functools import lru_cache
import json
from pathlib import Path
import tempfile

if __package__:
    from .course_sources import _github_text
else:
    from course_sources import _github_text


ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def source_reader():
    script = ROOT / "skills" / "Mathematics_Competition" / "scripts" / "scrape_cmathc.py"
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
        # Automatic fallback may need an OCR workspace; never put material caches in the project.
        with tempfile.TemporaryDirectory(prefix="course-skill-reference-") as work:
            official = module.excerpts(keywords, cache_dir=Path(work), log=log)
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
    for filename in ("mathnet_calculus.json", "ocw_calculus.json"):
        try:
            data = json.loads(_github_text("Practice/Mathematics_Competition/Open_Problems/" + filename))
            items = data["problems"]
            if not isinstance(items, list):
                raise ValueError("开放选题格式无效")
            for item in items:
                if chapter not in item["modules"] and "综合" not in chapter:
                    continue
                parts.append(f"【Assistant_course 在线开放练习参考，非全国竞赛真题】{item['id']}\n{item['problem']}\n"
                             f"来源：{item['source']}\n许可：{item['license']}\n署名：{item['attribution']}\n改动：{item['changes']}")
                if sum(map(len, parts)) > 11000:
                    break
        except (OSError, ValueError, KeyError, TypeError) as error:
            log(f"GitHub 开放选题读取未完成：{error}")
    status = "已提供实际在线读取的真题文本；来源留作内部核验，改编题只标“改编”，不逐题打印出处，不得编造届次或题号。" if official else "未核验真题参考：本次没有取得可用的真题正文，只能标为模拟训练。"
    log(status)
    return status + "\n\n" + "\n\n".join(parts)

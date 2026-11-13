"""Read subject material from the public GitHub library, with optional local/offline use."""

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import re
import time
import urllib.error
import urllib.parse
import urllib.request

if __package__:
    from .skill_rules import SUBJECT_DIRS, SUBJECT_MODULES
else:
    from skill_rules import SUBJECT_DIRS, SUBJECT_MODULES

ROOT = Path(__file__).resolve().parent.parent
LIBRARY_REPO = "https://github.com/Lyric-zephyr/Assistant_course"
LIBRARY_RAW = "https://raw.githubusercontent.com/Lyric-zephyr/Assistant_course/main/"
LIBRARY_TREE = "https://api.github.com/repos/Lyric-zephyr/Assistant_course/git/trees/main?recursive=1"
OCW = "https://ocw.mit.edu"
OCW_COURSE = OCW + "/courses/18-04-complex-variables-with-applications-spring-2018/"


def library_root():
    return Path(os.environ.get("COURSE_SKILL_LIBRARY") or ROOT.parent / "Assistant_course").expanduser().resolve()


def _score(text, keywords):
    text = text.casefold()
    return sum(min(6, text.count(word.casefold())) for word in keywords)


def _excerpts(text, keywords, limit):
    # Score non-overlapping windows, then restore reading order within each file.
    windows = [(offset, text[offset:offset + 1400]) for offset in range(0, len(text), 1400)]
    ranked = sorted(windows, key=lambda item: _score(item[1], keywords), reverse=True)
    selected, remaining = [], limit
    for offset, chunk in ranked:
        if remaining <= 0 or not _score(chunk, keywords):
            break
        selected.append((offset, chunk[:remaining]))
        remaining -= len(chunk)
    return "\n[…节选…]\n".join(chunk for _, chunk in sorted(selected))


def _material_rank(path, item, keywords, module=None):
    metadata = " ".join(str(item.get(key, "")) for key in ("title", "keywords", "preview"))
    score = _score(metadata, keywords)
    edition = re.search(r"Edition_(\d+)", str(path))
    return (bool(module and module in item.get("modules", [])),
            item.get("kind") == "exercise", bool(score),
            item.get("role") in ("Questions", "Questions_and_Solutions"),
            item.get("kind") == "cleaned_notes", item.get("kind") in ("textbook_section", "textbook_chapter"),
            "Non_Mathematics_A" in path.parts,
            score, "Community_Transcript" in str(path), int(edition[1]) if edition else 0)


def _module_key(subject, chapter):
    rule = SUBJECT_MODULES[subject].get(chapter)
    return Path(rule[0]).stem if rule and "comprehensive" not in rule[0] else None


def _select_materials(records, keywords, module, limit=12):
    eligible = [(path, item) for path, item in records.items()
                if item.get("kind") != "archive"
                and (not module or not item.get("modules") or module in item["modules"])]
    ranked = sorted(eligible, key=lambda record: _material_rank(
        PurePosixPath(str(record[0])), record[1], keywords, module), reverse=True)
    # Give each textbook section a turn before reading more parts of the same section.
    first, extra, seen = [], [], set()
    for record in ranked:
        item = record[1]
        group = ((item.get("volume"), item.get("chapter"), item.get("section"))
                 if item.get("kind") == "textbook_section" else str(record[0]))
        (extra if group in seen else first).append(record)
        seen.add(group)
    ordered = first + extra
    # Chapter practice also keeps a relevant whole-paper reference available.
    if module and any(item.get("kind") == "exercise" for _, item in ordered):
        paper = next((record for record in ordered if record[1].get("kind") == "past_paper"), None)
        if paper is not None:
            ordered.remove(paper)
            ordered.insert(1, paper)
    paired, included = [], set()
    for record in ordered:
        if str(record[0]) in included:
            continue
        paired.append(record)
        included.add(str(record[0]))
        # Read one matching answer counterpart next to its question; other answer
        # batches retain their normal rank instead of exhausting the entire budget.
        partners = record[1].get("paired_paths", [])
        if not isinstance(partners, list):
            continue
        for other in ranked:
            name = str(other[0]).replace("\\", "/")
            if str(other[0]) not in included and any(isinstance(partner, str) and
                    (name == partner or name.endswith("/" + partner)) for partner in partners):
                paired.append(other)
                included.add(str(other[0]))
                break
    return paired[:limit]


def _module_outline(records, module):
    titles = dict.fromkeys(item["title"] for item in records.values()
                           if module and module in item.get("modules", [])
                           and item.get("kind") == "textbook_section" and item.get("title"))
    return ("【本模块教材目录（索引信息；下方实际读取的节选才是正文）】\n"
            + "\n".join(titles)[:2400] + "\n\n") if titles else ""


def _material_excerpt(text, item, keywords, limit, module):
    if module and item.get("topic_spans"):
        if not isinstance(item["topic_spans"], list):
            return ""
        lines = text.splitlines()
        fragments = []
        for span in item["topic_spans"]:
            if not isinstance(span, dict) or module not in span.get("modules", []):
                continue
            interval = span.get("lines")
            if (not isinstance(interval, list) or len(interval) != 2
                    or not all(type(value) is int for value in interval)
                    or not 1 <= interval[0] <= interval[1] <= len(lines)):
                continue
            fragments.append(f"【原资料定位：{span.get('label', '')}】\n"
                             + "\n".join(lines[interval[0]-1:interval[1]]))
        if not fragments:
            return ""
        text = "\n\n".join(fragments)
    excerpt = _excerpts(text, keywords, limit)
    # Explicit module metadata also covers synonyms and OCR-damaged keywords.
    return excerpt or (text[:limit] if module and module in item.get("modules", []) else "")


def _library_path(value, prefix, extensions=(".md", ".txt")):
    """Index entries may name only ordinary text files inside the requested subject/mode."""
    if (not isinstance(value, str) or not value.startswith(prefix + "/")
            or "\\" in value or ":" in value or any(ord(c) < 32 for c in value)
            or any(part in ("", ".", "..") for part in value.split("/"))):
        return False
    path = PurePosixPath(value)
    return ("Chapters" not in path.parts and path.suffix.lower() in extensions
            and path.name.lower() not in ("readme.md", "license.txt"))


@lru_cache(maxsize=32)
def _github_fetch(path, interval):
    # Small, bounded process-memory cache, refreshed every five minutes; no material files on disk.
    url = LIBRARY_TREE if path is None else LIBRARY_RAW + urllib.parse.quote(path, safe="/")
    request = urllib.request.Request(url, headers={"User-Agent": "CourseSkill/1.0 (public material reader)"})
    with urllib.request.urlopen(request, timeout=10) as response:
        if urllib.parse.urlparse(response.url).hostname not in ("raw.githubusercontent.com", "api.github.com"):
            raise ValueError("资料链接未返回 GitHub 正文，已跳过。")
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
            raise ValueError("GitHub 返回网页而非资料正文，已跳过。")
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError("单份在线资料超过 2 MB，已跳过。")
    return data.decode("utf-8-sig")


def _github_text(path):
    return _github_fetch(path, int(time.monotonic() // 300))


def _github_records(prefix):
    """Use a subject index first, the existing math manifest second, then GitHub's file tree."""
    for filename, key in (("index.json", "items"), ("manifest.json", "sources")):
        try:
            data = json.loads(_github_text(prefix + "/" + filename))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                continue
            raise
        items = data.get(key) if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ValueError(f"在线 {filename} 的 {key} 不是资料列表。")
        records = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            path = item.get("path") if key == "items" else prefix + "/" + str(item.get("file", ""))
            if _library_path(path, prefix):
                records[path] = item
        if records:
            return records
    data = json.loads(_github_text(None))
    if not isinstance(data, dict) or data.get("truncated") or not isinstance(data.get("tree"), list):
        raise ValueError("GitHub 文件目录未完整返回。")
    return {item["path"]: {} for item in data["tree"] if isinstance(item, dict)
            and item.get("type") == "blob" and _library_path(item.get("path"), prefix)}


def load_github_materials(subject, mode, keywords, log=print, chapter=None):
    prefix = ("Course" if mode == "总结知识点" else "Practice") + "/" + SUBJECT_DIRS[subject]
    try:
        records = _github_records(prefix)
    except (OSError, ValueError) as error:
        log(f"GitHub 资料索引读取失败：{error}；尝试本地资料或后续参考。")
        return ""
    module = _module_key(subject, chapter)
    candidates = _select_materials(records, keywords, module)
    indexed = any(item.get("kind") == "textbook_section" for _, item in candidates)
    limit = min(2600, 12000 // max(1, len(candidates))) if indexed else 2600

    def read(record):
        path, item = record
        try:
            return path, item, _material_excerpt(_github_text(path), item, keywords, limit, module)
        except (OSError, ValueError):
            return path, item, ""

    parts, remaining = [], 12000
    # Bounded parallel reads avoid serial network waits without fetching the whole library.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for path, item, excerpt in pool.map(read, candidates):
            if len(excerpt.strip()) < 80 or remaining <= 0 or len(parts) >= (12 if indexed else 7):
                continue
            excerpt = excerpt[:remaining]
            url = LIBRARY_RAW + urllib.parse.quote(path, safe="/")
            parts.append(f"【GitHub 实际读取：{path}；质量：{item.get('quality', '未校订文本')}】\n{url}\n{excerpt}")
            remaining -= len(excerpt)
    if parts:
        log(f"已从 GitHub Assistant_course/{prefix} 读取 {len(parts)} 份相关文本节选，无需下载资料包。")
    else:
        log(f"GitHub Assistant_course/{prefix} 未取得相关正文，尝试本地资料或后续参考。")
    return _module_outline(records, module) + "\n\n".join(parts) if parts else ""


def load_course_materials(subject, mode, keywords, log=print, root=None, chapter=None):
    """Default to the public library; explicit local overrides and offline fallback remain available."""
    if root is not None or os.environ.get("COURSE_SKILL_LIBRARY"):
        return _load_local_materials(subject, mode, keywords, log=log, root=root, chapter=chapter)
    return (load_github_materials(subject, mode, keywords, log=log, chapter=chapter)
            or _load_local_materials(subject, mode, keywords, log=log, chapter=chapter))


def _load_local_materials(subject, mode, keywords, log=print, root=None, chapter=None):
    """Summary reads Course only; practice reads Practice only. Index paths stay in that subject."""
    root = Path(root).resolve() if root is not None else library_root()
    category = "Course" if mode == "总结知识点" else "Practice"
    folder = (root / category / SUBJECT_DIRS[subject]).resolve()
    if not folder.is_relative_to(root) or not folder.is_dir():
        log(f"资料库暂无 {category}/{SUBJECT_DIRS[subject]}，继续使用后续参考。")
        return ""
    records, archives = {}, set()
    index = folder / "index.json"
    if index.is_file():
        try:
            data = json.loads(index.read_text(encoding="utf-8-sig"))
            items = data.get("items", [])
            if not isinstance(items, list):
                raise ValueError("items 应为资料列表")
            archives = {(root / item["path"]).resolve() for item in data.get("originals", [])
                        if isinstance(item, dict) and isinstance(item.get("path"), str)}
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    continue
                path = (root / item["path"]).resolve()
                if path.is_relative_to(folder) and path.suffix.lower() in (".md", ".txt") and path.is_file():
                    records[path] = item
        except (OSError, ValueError, AttributeError) as error:
            log(f"资料索引不可用，改为按正文查找：{error}")
    # Also include unindexed user additions; do not read source manifests as content.
    for path in folder.rglob("*"):
        if "Chapters" in path.relative_to(folder).parts:
            continue
        if path.suffix.lower() not in (".md", ".txt") or path.name.lower() in ("readme.md", "license.txt", "contents.md"):
            continue
        path = path.resolve()
        if path.is_relative_to(folder) and path.is_file() and path not in archives:
            records.setdefault(path, {})

    module = _module_key(subject, chapter)
    candidates = _select_materials(records, keywords, module, limit=None)
    indexed = any(item.get("kind") == "textbook_section" for _, item in candidates)
    if indexed:
        candidates = candidates[:12]
    limit = min(2600, 12000 // max(1, len(candidates))) if indexed else 2600
    parts, remaining = [], 12000
    for path, item in candidates:
        if remaining <= 0 or len(parts) >= (12 if indexed else 7):
            break
        try:
            # Study files are plain text. Cap unusually large files and prompt fragments.
            with path.open(encoding="utf-8-sig", errors="replace") as source:
                text = source.read(2_000_000)
        except OSError:
            continue
        excerpt = _material_excerpt(text, item, keywords, min(limit, remaining), module)
        if len(excerpt.strip()) < 80:
            continue
        quality = item.get("quality", "未校订文本")
        parts.append(f"【本地资料：{path.relative_to(root).as_posix()}；质量：{quality}】\n{excerpt}")
        remaining -= len(excerpt)
    if not parts:
        log(f"资料库 {category}/{SUBJECT_DIRS[subject]} 未找到本模块相关正文，使用后续参考。")
        return ""
    log(f"已读取 {category}/{SUBJECT_DIRS[subject]} 的 {len(parts)} 份相关文本节选。")
    return _module_outline(records, module) + "\n\n".join(parts)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href:
                self.links.append(href)


def _ocw_read(url, limit=6_000_000):
    if urllib.parse.urlparse(url).hostname != "ocw.mit.edu":
        raise ValueError("仅从 MIT OCW 官网读取补充习题。")
    request = urllib.request.Request(url, headers={"User-Agent": "CourseSkill/1.0 (study material reader)"})
    with urllib.request.urlopen(request, timeout=10) as response:
        if urllib.parse.urlparse(response.url).hostname != "ocw.mit.edu":
            raise ValueError("MIT OCW 资料跳转至其他站点，已跳过。")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("MIT OCW 单份资料过大，已跳过。")
    return data


def load_complex_practice(keywords, log=print):
    """Fallback: discover OCW exercise PDFs, extract in memory, and keep relevant text only."""
    terms = list(keywords)
    translations = {"复数": "complex", "辐角": "argument", "解析函数": "analytic", "C-R": "Cauchy-Riemann",
                    "调和": "harmonic", "保形": "conformal", "复积分": "integral", "柯西": "Cauchy",
                    "原函数": "antiderivative", "幂级数": "power series", "泰勒": "Taylor", "洛朗": "Laurent",
                    "留数": "residue", "奇点": "singular", "极点": "pole", "傅里叶": "Fourier",
                    "拉普拉斯": "Laplace", "卷积": "convolution"}
    terms.extend(value for key, value in translations.items() if any(key in word for word in keywords))
    try:
        import fitz
        page = OCW_COURSE + "pages/problem-sets-and-solutions/"
        parser = _Links()
        parser.feed(_ocw_read(page).decode("utf-8"))
        resources = list(dict.fromkeys(urllib.parse.urljoin(page, href) for href in parser.links
                                      if "/resources/" in href and "ps" in href.lower()))
        # Verified 18.04 problem-set syllabus: 1 numbers, 2 analytic, 3/4 integrals,
        # 5 harmonic, 6 series/residues, 7 real integrals, 8/9 conformal/argument principle.
        topics = " ".join(terms).casefold()
        preferred = []
        for words, numbers in ((("complex", "argument"), (1,)),
                               (("analytic", "harmonic", "conformal"), (2, 5, 8)),
                               (("cauchy", "antiderivative", "integral"), (3, 4)),
                               (("series", "taylor", "laurent"), (6,)),
                               (("residue", "singular", "pole"), (7, 6, 9))):
            if any(word in topics for word in words):
                preferred.extend(n for n in numbers if n not in preferred)

        def priority(url):
            match = re.search(r"pset(\d+)", url)
            number = int(match[1]) if match else None
            return (preferred.index(number) if number in preferred else len(preferred),
                    -_score(url.replace("-", " "), terms))

        resources.sort(key=priority)
        parts, seen = [], set()
        # Keep a question set and its solution together when available.
        for resource in resources[:4]:
            links = _Links()
            links.feed(_ocw_read(resource).decode("utf-8"))
            for href in links.links:
                url = urllib.parse.urljoin(resource, href)
                if not urllib.parse.urlparse(url).path.lower().endswith(".pdf") or url in seen:
                    continue
                seen.add(url)
                with fitz.open(stream=_ocw_read(url), filetype="pdf") as document:
                    if document.needs_pass or not document.permissions & fitz.PDF_PERM_COPY:
                        continue
                    text = "\n".join(page.get_text() for page in document)
                excerpt = _excerpts(text, terms, 2400)
                if excerpt:
                    parts.append(f"【MIT OCW 实际读取；CC BY-NC-SA；仅作改编参考】{url}\n{excerpt}")
                break
            if len(parts) >= 2:
                break
        if parts:
            log(f"已从 MIT OCW 读取 {len(parts)} 份相关习题正文；不在项目中保存 PDF。")
            return "\n\n".join(parts)
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        log(f"MIT OCW 补充资料读取未完成：{error}")
    log("未取得相关 MIT OCW 习题正文，按模块范围自主设计，不声称引用网站题目。")
    return ""

"""运行时建立真题索引并按需在线读取；索引及 OCR 缓存在 local_problems。"""

import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import quote, unquote, urljoin, urlsplit
import urllib.request
import urllib.error


ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "local_problems"
SEEDS = ("http://www.cmathc.cn/article/list_2.html", "https://www.cmathc.org.cn/csst/",
         "https://www.cmathc.org.cn/st/560.html")
LIMIT = 12 * 1024 * 1024
SCHEMA_VERSION = 2
USER_AGENT = "MathCompSkill/1.0 (local study reference)"
_ROBOTS = {}
_LAST_REQUEST = {}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.href, self.label = [], None, ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href, self.label = dict(attrs).get("href"), ""

    def handle_data(self, data):
        if self.href is not None:
            self.label += data

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            self.links.append((self.href, re.sub(r"\s+", " ", self.label).strip()))
            self.href = None


def _allowed(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    return parsed.scheme in ("https", "http") and any(host == domain or host.endswith("." + domain)
                                                        for domain in ("cmathc.cn", "cmathc.org.cn"))


def _robots(url):
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
    if origin in _ROBOTS and time.time() - _ROBOTS[origin].get("fetched_at", 0) < 3600:
        return _ROBOTS[origin]
    robots_url = origin + "/robots.txt"
    try:
        with urllib.request.urlopen(urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT}), timeout=6) as response:
            body = response.read(256000).decode("utf-8", errors="replace")
            if "<html" in body.lower() or not _allowed(response.url):
                raise ValueError("robots.txt 返回非规则页面或站外重定向。")
        result = {"url": robots_url, "status": "checked", "body": body}
    except urllib.error.HTTPError as error:
        result = {"url": robots_url, "status": "not_present" if error.code in (404, 410) else "unavailable", "body": "", "http_status": error.code}
    except (OSError, ValueError) as error:
        result = {"url": robots_url, "status": "unavailable", "body": "", "reason": str(error)}
    result["fetched_at"] = time.time()
    _ROBOTS[origin] = result
    return result


def source_access(url):
    if not _allowed(url):
        return {"status": "manual", "reason": "站外入口，需要用户在原网页查看。"}
    policy = _robots(url)
    result = {"robots_url": policy["url"], "robots_status": policy["status"],
              "checked_at": time.strftime("%Y-%m-%d"), "delay": 0.4}
    if policy["status"] == "unavailable":
        return dict(result, status="unknown", reason="暂时无法核对 robots.txt，暂停自动读取。")
    groups, agents, rules = [], [], []
    for line in policy["body"].splitlines() + ["User-agent: __end__"]:
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key.lower() == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
        elif agents:
            rules.append((key.lower(), value))
    applicable = [(1 if any(agent != "*" and agent in USER_AGENT.lower() for agent in names) else 0, entries)
                  for names, entries in groups if any(agent == "*" or agent in USER_AGENT.lower() for agent in names)]
    chosen = max((score for score, _ in applicable), default=-1)
    path = urlsplit(url).path + ("?" + urlsplit(url).query if urlsplit(url).query else "")
    matches = []
    for score, entries in applicable:
        if score != chosen:
            continue
        for key, pattern in entries:
            if key == "crawl-delay":
                try:
                    result["delay"] = max(result["delay"], float(pattern))
                except ValueError:
                    pass
            elif key in ("allow", "disallow") and pattern:
                expression = re.escape(pattern).replace(r"\*", ".*")
                if expression.endswith(r"\$"):
                    expression = expression[:-2] + "$"
                if re.match(expression, path):
                    matches.append((len(pattern.replace("*", "").rstrip("$")), key == "allow", pattern))
    if matches and not max(matches)[1]:
        return dict(result, status="blocked", reason="robots.txt 禁止自动访问：" + max(matches)[2])
    return dict(result, status="allowed", reason="未发现适用于此路径的 robots 禁止规则；不代表获得版权许可。")


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        access = source_access(newurl)
        if access["status"] != "allowed":
            raise PermissionError(access["reason"])
        return super().redirect_request(request, response, code, message, headers, newurl)


def _fetch(url, timeout=8):
    if not _allowed(url):
        raise ValueError("仅自动下载 cmathc.cn / cmathc.org.cn 上的资料。")
    access = source_access(url)
    if access["status"] != "allowed":
        raise PermissionError(access["reason"])
    if access["delay"] > 30:
        raise PermissionError("站点要求较长抓取间隔，请在原网页人工查看。")
    origin = urlsplit(url).netloc
    time.sleep(max(0, access["delay"] - (time.monotonic() - _LAST_REQUEST.get(origin, 0))))
    _LAST_REQUEST[origin] = time.monotonic()
    request = urllib.request.Request(quote(url, safe=":/?=&%+@"), headers={"User-Agent": USER_AGENT})
    with urllib.request.build_opener(CheckedRedirect()).open(request, timeout=timeout) as response:
        if not _allowed(response.url):
            raise ValueError("资料重定向至站外，请人工检查来源。")
        data = response.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError("资料超过 12 MB 下载上限。")
        encoding = response.headers.get_content_charset()
        if not encoding and urlsplit(url).hostname == "www.cmathc.cn":
            encoding = "gb18030"
        return data, encoding or "utf-8"


def _category(text):
    text = re.sub(r"\s+", "", unquote(text)).upper()
    if re.search(r"非数(?:学)?(?:类)?[AＡ]", text):
        return "非数A"
    if re.search(r"非数(?:学)?(?:类)?[BＢ]", text):
        return "非数B"
    if re.search(r"(?<!非)数学(?:类)?[AＡ]", text):
        return "数学A"
    if re.search(r"(?<!非)数学(?:类)?[BＢ]", text):
        return "数学B"
    if "非数学" in text:
        return "非数学（旧届未分A/B）"
    if "数学类" in text:
        return "数学类（旧届未分A/B）"
    return None


def _edition(text):
    match = re.search(r"第?\s*([0-9一二三四五六七八九十]+)\s*届", unquote(text))
    if not match:
        return None
    number = match[1]
    if number.isdigit():
        return int(number)
    digits = {character: value for value, character in enumerate("零一二三四五六七八九")}
    if "十" in number:
        left, right = number.split("十", 1)
        return (digits.get(left, 1) * 10) + digits.get(right, 0)
    return digits.get(number)


def _save_index(cache_dir, sources, errors):
    editions = []
    for edition in range(1, 18):
        entries = [source for source in sources if source.get("edition") == edition]
        statuses = {source["access"]["status"] for source in entries}
        status = "online_available" if "allowed" in statuses else "manual_or_restricted" if entries else "missing"
        editions.append({"edition": edition, "status": status, "source_count": len(entries),
                         "cached_count": sum(source.get("download_status") == "downloaded" for source in entries)})
    report = {"schema_version": SCHEMA_VERSION, "checked_at": time.strftime("%Y-%m-%d"),
              "mode": "online-first", "copyright": "No redistribution or AI-service-upload license verified.",
              "sources": sources, "editions": editions, "errors": errors, "access_checks": list(_ROBOTS.values())}
    (cache_dir / "sources.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    import html
    rows = []
    for item in editions:
        links = [f'<a href="{html.escape(source["page_url"], quote=True)}">{html.escape(source["title"])}</a> '
                 f'({html.escape(source["access"]["status"])}: {html.escape(source["access"]["reason"])})'
                 for source in sources if source.get("edition") == item["edition"]]
        rows.append(f'<tr><td>第 {item["edition"]} 届</td><td>{item["status"]}</td><td>' + '<br>'.join(links or ["未发现可核对入口，不代表该届不存在资料。"]) + '</td></tr>')
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>1–17 届真题来源与访问状态</title>'
    page += '<style>body{font:16px/1.7 sans-serif;margin:2em}td,th{border:1px solid #aaa;padding:8px}table{border-collapse:collapse}a{color:#1565c0}</style>'
    page += '<h1>第 1–17 届资料来源索引</h1><p>这是来源及访问状态清单，不表示已完整下载。受限入口请在原网页查看；登录、验证码、robots 禁止和版权条件均不可绕过。在线读取仍是网络获取，不构成版权许可。</p>'
    page += '<table><tr><th>届次</th><th>状态</th><th>来源网页及原因</th></tr>' + ''.join(rows) + '</table></html>'
    (cache_dir / "source_index.html").write_text(page, encoding="utf-8")
    return report


def collect(cache_dir=CACHE, refresh=False, log=print, download_all=False):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    index = cache_dir / "sources.json"
    previous = []
    if index.is_file():
        try:
            report = json.loads(index.read_text(encoding="utf-8"))
            previous = report["sources"]
            if not refresh and report.get("schema_version") == SCHEMA_VERSION and time.time() - index.stat().st_mtime < 86400:
                if not download_all:
                    return previous
        except (ValueError, KeyError):
            pass
    queue = [(url, "", None) for url in SEEDS]
    visited, candidates, errors = set(), {}, []
    deadline = time.monotonic() + 180
    while queue and len(visited) < 65 and time.monotonic() < deadline:
        url, page_title, parent_edition = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            data, encoding = _fetch(url)
            parser = Links()
            parser.feed(data.decode(encoding, errors="replace"))
            log(f"索引进度 [{len(visited)}]：{page_title or url}")
        except (OSError, ValueError) as error:
            errors.append({"url": url, "reason": str(error)})
            log(f"索引无法读取：{url}（{error}）")
            continue
        for href, label in parser.links:
            target = urljoin(url, href).split("#")[0]
            label = label.strip()
            combined = label + " " + unquote(target)
            edition = _edition(combined) or parent_edition
            if edition is not None and not 1 <= edition <= 17:
                continue
            if any(word in label for word in ("获奖", "名单", "报名", "通知", "南昌", "浙江")):
                continue
            pdf = urlsplit(target).path.lower().endswith(".pdf")
            paper = any(word in label for word in ("试题", "真题", "试卷", "参考解答", "参考答案"))
            if pdf and edition:
                category = _category(combined) or _category(page_title) or "综合资料（类别未核验）"
                candidates[target] = {"url": target, "title": label or page_title, "page_url": url,
                                      "edition": edition, "category": category, "kind": "pdf"}
            elif paper and edition and not _allowed(target) and urlsplit(target).scheme in ("http", "https"):
                candidates[target] = {"url": target, "title": label, "page_url": url, "edition": edition,
                                      "category": _category(label) or "综合资料（类别未核验）", "kind": "external_page"}
            elif _allowed(target) and target not in visited:
                path = urlsplit(target).path
                listing = bool(re.search(r"/article/list_2(?:_\d+)?\.html$|/csst(?:_\d+)?/$", path))
                article = paper and edition and bool(re.search(r"/article/\d+\.html$|/csst/\d+\.html$", path))
                if (listing or article) and all(target != queued[0] for queued in queue):
                    queue.append((target, label, edition))
    if queue:
        errors.append({"reason": "达到本次索引时间/页数上限；未访问的入口保留待后续核对。", "remaining": len(queue)})
    old_by_url = {source["url"]: source for source in previous}
    for target, source in candidates.items():
        source.update(access=source_access(target), accessed=time.strftime("%Y-%m-%d"),
                      rights="Copyright retained; no redistribution or AI-upload license verified.")
        old = old_by_url.get(target, {})
        if old.get("file"):
            source["file"] = old["file"]
            source["download_status"] = "legacy_cache_not_authorization"
        if download_all and source["kind"] == "pdf" and source["access"]["status"] == "allowed":
            digest = hashlib.sha256(target.encode("utf-8")).hexdigest()[:20]
            pdf = cache_dir / f"{digest}.pdf"
            try:
                if not pdf.is_file():
                    data, _ = _fetch(target, timeout=12)
                    if not data.startswith(b"%PDF-"):
                        raise ValueError("下载内容不是 PDF，可能需要登录或验证。")
                    pdf.write_bytes(data)
                source.update(file=pdf.name, download_status="downloaded")
                log(f"已下载第 {source['edition']} 届：{source['title']}")
            except (OSError, ValueError) as error:
                source.update(download_status="failed", download_error=str(error))
                log(f"下载未完成：{source['title']}（{error}）")
        elif download_all:
            source["download_status"] = "skipped_access_restriction"
    # 保留历史缓存记录供用户查看；再次使用前仍需重新检查访问限制。
    for target, source in old_by_url.items():
        if target not in candidates:
            source.update(access=source_access(target), edition=source.get("edition") or _edition(source["title"]),
                          kind=source.get("kind", "pdf"), download_status="legacy_cache_not_authorization")
            candidates[target] = source
    sources = sorted(candidates.values(), key=lambda source: (source.get("edition") or 99, source["category"], source["url"]))
    report = _save_index(cache_dir, sources, errors)
    available = [entry["edition"] for entry in report["editions"] if entry["status"] == "online_available"]
    log(f"1–17 届状态已逐届记录；有未发现 robots 禁止规则的 PDF 入口的届次：{available}（尚不表示逐份读取成功）。完整报告：{cache_dir / 'source_index.html'}")
    return sources


def excerpts(chapter_keywords, cache_dir=CACHE, log=print):
    import pymupdf

    sources = collect(cache_dir, log=log)
    result = []
    priority = {"非数A": 0, "非数学（旧届未分A/B）": 1, "非数B": 2, "数学A": 3}
    sources = sorted(sources, key=lambda source: (priority.get(source["category"], 9), -(source.get("edition") or 0)))
    for source in sources:
        if source.get("kind") != "pdf" or source["category"] not in priority:
            continue
        access = source_access(source["url"])
        if access["status"] != "allowed":
            continue
        digest = hashlib.sha256(source["url"].encode("utf-8")).hexdigest()[:20]
        pdf = Path(cache_dir) / f"{digest}.pdf"
        selected = []
        try:
            # 优先在线读取；只有用户运行 --download-all 时才保存原始 PDF。
            # 历史缓存不能绕过当前的 robots 访问限制。
            data, _ = _fetch(source["url"], timeout=12)
            if not data.startswith(b"%PDF-"):
                raise ValueError("文件不是可直接读取的 PDF；请在原网页完成登录或验证。")
            with pymupdf.open(stream=data, filetype="pdf") as document:
                if document.needs_pass or not (document.permissions & pymupdf.PDF_PERM_COPY):
                    raise PermissionError("PDF 有密码或复制权限限制，停止自动提取，请在原站核对授权。")
                pages = [(number + 1, page.get_text()) for number, page in enumerate(document)]
                if not any(any(keyword in text for keyword in chapter_keywords) for _, text in pages):
                    ocr_file = pdf.with_suffix(".ocr.json")
                    cached = json.loads(ocr_file.read_text(encoding="utf-8")) if ocr_file.is_file() else []
                    wanted = sorted({0, min(1, len(document) - 1), min(2, len(document) - 1), len(document) - 2, len(document) - 1} - {-1})
                    if cached and {item["page"] for item in cached}.issuperset(number + 1 for number in wanted):
                        pages = [(item["page"], item["text"]) for item in cached]
                    elif os.name == "nt" and shutil.which("powershell"):
                        log(f"真题为扫描件或缺少可用文本，正在用 Windows OCR 读取题目及后部压轴页：{source['title']}")
                        with tempfile.TemporaryDirectory(prefix=".ocr-", dir=cache_dir) as work:
                            for number in wanted:
                                document[number].get_pixmap(dpi=180).save(Path(work) / f"{number + 1:03d}.png")
                            ocr_result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                                     str(Path(__file__).with_name("ocr_windows.ps1")), "-ImageDirectory", work],
                                                    capture_output=True, encoding="utf-8", errors="replace", timeout=90,
                                                    creationflags=subprocess.CREATE_NO_WINDOW, check=True)
                            data = json.loads(ocr_result.stdout)
                            ocr_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                            pages = [(item["page"], item["text"]) for item in data]
                matches = []
                for number, text in pages:
                    text = re.sub(r"(?<=[\u3400-\u9fff])[ \t]+(?=[\u3400-\u9fff])", "", text)
                    if any(keyword in text for keyword in chapter_keywords):
                        matches.append((number, text))
                for number, text in (matches if len(matches) < 2 else [matches[0], matches[-1]]):
                    selected.append(f"第 {number} 页（PDF 提取或 OCR，仅作参考，需核对原图公式）：\n{text[:1000]}")
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            log(f"PDF 文本提取失败：{source['title']}（{error}）")
        if selected:
            result.append(f"【已实际获取：{source['category']}】{source['title']}\n来源：{source['url']}\n" + "\n".join(selected))
        if len(result) >= 4:
            break
    if not result:
        log("没有可用的真题正文；将明确标为未核验真题参考，不能宣称已参考官网。")
    return result


def main():
    parser = argparse.ArgumentParser(description="建立第1–17届来源索引；尊重访问限制，默认不保存远程PDF。")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--download-all", action="store_true", help="尝试下载1–17届全部已发现且允许自动访问的PDF；受限或缺失项逐一报告")
    parser.add_argument("--cache-dir", type=Path, default=CACHE)
    args = parser.parse_args()
    sources = collect(args.cache_dir, args.refresh, download_all=args.download_all)
    print(f"已记录 {len(sources)} 个来源；并非全部已下载。逐届报告：{args.cache_dir / 'source_index.html'}")


if __name__ == "__main__":
    main()

import json
from pathlib import Path
import re

import pytest

from adapters import ai_runtime, course_sources, practice_history, skill_rules


def material(root, category, subject, name, text):
    path = root / category / subject / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_index_reader_confines_subject_and_task(tmp_path):
    good = material(tmp_path, "Course", "Complex_Analysis", "notes.md", "复数的几何表示与运算。" * 30)
    material(tmp_path, "Practice", "Complex_Analysis", "questions.md", "复数 PRACTICE_ONLY " * 20)
    material(tmp_path, "Course", "Mathematics_Competition", "notes.md", "复数 WRONG_SUBJECT " * 20)
    (tmp_path / "private.md").write_text("复数 ESCAPED_CONTENT " * 20, encoding="utf-8")
    index = {"items": [{"path": path} for path in (
        str(good.relative_to(tmp_path)), "Practice/Complex_Analysis/questions.md",
        "Course/Mathematics_Competition/notes.md", "private.md", "../outside.md")]}
    (good.parent / "index.json").write_text(json.dumps(index), encoding="utf-8")
    text = course_sources.load_course_materials("复变函数", "总结知识点", ("复数",), root=tmp_path, log=lambda *_: None)
    assert "几何表示" in text
    assert all(marker not in text for marker in ("PRACTICE_ONLY", "WRONG_SUBJECT", "ESCAPED_CONTENT"))


def test_reader_prefers_clean_notes_and_bounds_context(tmp_path):
    material(tmp_path, "Course", "Complex_Analysis", "ocr.md", "复数 OCR " * 5000)
    clean = material(tmp_path, "Course", "Complex_Analysis", "notes.md", "复数 CLEAN " * 5000)
    index = {"items": [{"path": clean.relative_to(tmp_path).as_posix(), "title": "复数",
                         "kind": "cleaned_notes", "quality": "visually_reconstructed"}]}
    (clean.parent / "index.json").write_text(json.dumps(index), encoding="utf-8")
    text = course_sources.load_course_materials("复变函数", "总结知识点", ("复数",), root=tmp_path, log=lambda *_: None)
    assert text.index("CLEAN") < text.index("OCR")
    assert len(text) < 14000


def test_prompt_uses_pdf_then_course_and_practice_does_not_fetch_when_local(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_SKILL_LIBRARY", str(tmp_path))
    material(tmp_path, "Course", "Complex_Analysis", "notes.md", "复数 LOCAL_COURSE " * 30)
    material(tmp_path, "Practice", "Complex_Analysis", "paper.md", "复数 LOCAL_PRACTICE " * 30)
    monkeypatch.setattr(course_sources, "load_complex_practice", lambda *a, **k: pytest.fail("Unnecessary network fallback"))
    chapter = next(iter(skill_rules.COMPLEX_MODULE_RULES))
    prompt = skill_rules.build_prompt("总结知识点", chapter, "USER_PDF", log=lambda *_: None)
    assert prompt.index("USER_PDF") < prompt.index("LOCAL_COURSE")
    assert "LOCAL_PRACTICE" not in prompt
    practice = skill_rules.build_prompt("练习", chapter, "", log=lambda *_: None)
    assert "LOCAL_PRACTICE" in practice and "LOCAL_COURSE" not in practice


def test_mit_fallback_extracts_pdf_without_saving(tmp_path, monkeypatch):
    import fitz
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((60, 60), "Residue problem: compute the contour integral of f(z).")
        pdf = document.tobytes()
    requests = []
    def read(url, **kwargs):
        requests.append(url)
        if url.endswith('.pdf'):
            return pdf
        if '/resources/' in url:
            return b'<a href="/courses/test/residue.pdf">download</a>'
        return b'<a href="/courses/test/resources/ps-residue/">Problem set</a>'
    monkeypatch.setattr(course_sources, "_ocw_read", read)
    text = course_sources.load_complex_practice(("留数",), log=lambda *_: None)
    assert "Residue problem" in text and requests[-1].endswith('.pdf')


def paper(subject):
    sections = skill_rules.practice_sections(subject)
    count = sum(len(numbers) for _, numbers in sections)
    parts = []
    for name in ("第一套", "第二套"):
        parts.append(f"## {name} 题目")
        for label, numbers in sections:
            parts.append(f"### {label}")
            for number in numbers:
                parts.append(f"#### 第 {number} 题\n\n题干 {name} {number}，计算相应函数。")
                if label == "二、选择题":
                    parts.append("A. 零\n\nB. 一\n\nC. 二\n\nD. 不存在")
    parts.append("## 答案与解析")
    for name in ("第一套", "第二套"):
        parts.append(f"## {name} 详细解析")
        parts.extend(f"#### 第 {number} 题\n\n解析。" for number in range(1, count + 1))
    return "\n\n".join(parts)


@pytest.mark.parametrize("subject,total", [("数学竞赛", 20), ("复变函数", 28)])
def test_paper_counts_order_and_selected_subject_validation(subject, total):
    chapter = next(iter(skill_rules.SUBJECT_MODULES[subject]))
    text = skill_rules.order_problem_set(paper(subject))
    skill_rules.validate_problem_set(text, chapter)
    assert len(practice_history.question_blocks(text)) == total
    assert text.index("第二套 题目") < text.index("答案与解析") < text.index("第一套 详细解析")
    broken = text.replace("#### 第 4 题", "#### 第 99 题", 1)
    with pytest.raises(ValueError):
        skill_rules.validate_problem_set(broken, chapter)


def test_complex_cannot_be_validated_as_ten_question_math():
    with pytest.raises(ValueError, match="14"):
        skill_rules.validate_problem_set(paper("数学竞赛"), next(iter(skill_rules.COMPLEX_MODULE_RULES)))


def test_history_isolates_subjects_and_preserves_old_math_location(tmp_path):
    with practice_history.history_file(next(iter(skill_rules.MODULE_RULES)), tmp_path) as math:
        assert math.parent == tmp_path
    with practice_history.history_file(next(iter(skill_rules.COMPLEX_MODULE_RULES)), tmp_path) as complex_path:
        assert complex_path.parent == tmp_path / "Complex_Analysis"
    assert math != complex_path


def test_bad_practice_structure_retries_before_history_save(tmp_path, monkeypatch):
    requests = []
    def generate(prompt):
        requests.append(prompt)
        return "incomplete" if len(requests) == 1 else paper("复变函数")
    monkeypatch.setattr(practice_history, "find_duplicates", lambda *a: [])
    chapter = next(iter(skill_rules.COMPLEX_MODULE_RULES))
    content = practice_history.generate_practice(chapter, "PROMPT", generate, directory=tmp_path, log=lambda *_: None)
    assert len(requests) == 2
    skill_rules.validate_problem_set(content, chapter)
    with practice_history.history_file(chapter, tmp_path) as history:
        assert len(practice_history.load_history(history, chapter)) == 28


def test_summary_assembles_topics_once_and_limits_error_count():
    requests, progress = [], []
    def generate(prompt):
        requests.append(prompt)
        if "本轮仅输出 `## 二、易错总结`" in prompt:
            return "## 二、易错总结\n\n" + "\n\n".join(f"### {n}. 易错条件\n\n简短提醒。" for n in range(1, 8))
        number = len(requests)
        return f"## 一、知识梳理\n\n### 1. 主题{number}\n\n条件与公式{number}。"
    content = ai_runtime._generate_summary(next(iter(skill_rules.COMPLEX_MODULE_RULES)), "PROMPT", generate, progress.append)
    assert content.count("## 一、知识梳理") == 1
    assert content.count("## 二、易错总结") == 1
    assert "### 2. 主题2" in content
    assert len(requests) == len(progress) == 3
    assert "主题1" in requests[1]


@pytest.mark.parametrize("subject", ["数学竞赛", "复变函数"])
def test_comprehensive_summary_keeps_subject_and_user_context(subject, monkeypatch):
    chapters = list(skill_rules.SUBJECT_MODULES[subject])
    prompts = []
    def build(mode, chapter, context):
        assert context == "USER_PDF"
        prompts.append(chapter)
        return chapter
    def generate(prompt):
        if "本轮仅输出 `## 二、易错总结`" in prompt:
            return "## 二、易错总结\n\n" + "\n".join(f"### {n}. 注意\n\n提醒。" for n in range(1, 8))
        if "本轮仅输出 `## 跨模块联系与方法选择`" in prompt:
            return "## 跨模块联系与方法选择\n\n联系。"
        return "## 一、知识梳理\n\n### 1. 主题\n\n知识。"
    monkeypatch.setattr(ai_runtime, "build_prompt", build)
    prompt = "【用户 PDF 教材（最高优先）】\nUSER_PDF\n\n【Assistant_course 课程库（次优先）】\nLIBRARY"
    content = ai_runtime._generate_summary(chapters[-1], prompt, generate, lambda *_: None)
    assert prompts == chapters[:-1]
    assert all(f"## {chapter}" in content for chapter in chapters[:-1])



@pytest.mark.parametrize("mode,category", [("总结知识点", "Course"), ("练习", "Practice")])
def test_github_materials_need_no_local_library_and_stay_in_subject(mode, category, monkeypatch):
    monkeypatch.delenv("COURSE_SKILL_LIBRARY", raising=False)
    prefix = category + "/Complex_Analysis"
    valid = prefix + "/Notes/复数.md"
    outside = ("Practice" if category == "Course" else "Course") + "/Complex_Analysis/other.md"
    requested = []
    def read(path):
        requested.append(path)
        if path == prefix + "/index.json":
            return json.dumps({"items": [
                {"path": valid, "title": "复数", "kind": "cleaned_notes"},
                {"path": outside}, {"path": prefix + "/../../private.md"},
                {"path": "https://example.test/secret.md"},
                {"path": prefix + "/../Mathematics_Competition/notes.md"}]})
        assert path == valid
        return "复数 REMOTE_COURSE_CONTENT " * 20
    monkeypatch.setattr(course_sources, "_github_text", read)
    monkeypatch.setattr(course_sources, "_load_local_materials", lambda *a, **k: pytest.fail("No local library required"))
    result = course_sources.load_course_materials("复变函数", mode, ("复数",), log=lambda *_: None)
    assert "REMOTE_COURSE_CONTENT" in result
    assert requested == [prefix + "/index.json", valid]
    assert course_sources.LIBRARY_RAW in result


def test_github_math_practice_reads_existing_manifest(monkeypatch):
    import urllib.error
    prefix = "Practice/Mathematics_Competition"
    old = "Edition_14/Preliminary/Non_Mathematics/Regular_Questions.md"
    recent = "Edition_17/Preliminary/Non_Mathematics_A/Regular_Community_Transcript_Questions_and_Solutions.md"
    def read(path):
        if path.endswith("/index.json"):
            raise urllib.error.HTTPError(path, 404, "Not found", {}, None)
        if path.endswith("/manifest.json"):
            return json.dumps({"sources": [{"file": old}, {"file": recent}, {"file": "../../Course/notes.md"}]})
        assert path in (prefix + "/" + old, prefix + "/" + recent)
        return "极限与连续 MATH_PAPER " * 20
    monkeypatch.setattr(course_sources, "_github_text", read)
    result = course_sources.load_github_materials("数学竞赛", "练习", ("极限",), log=lambda *_: None)
    assert "MATH_PAPER" in result and result.index(recent) < result.index(old)


def test_github_tree_discovers_unindexed_textbooks_without_fixed_book_names(monkeypatch):
    import urllib.error
    prefix = "Course/Mathematics_Competition"
    valid = prefix + "/Another_Textbook.md"
    requested = []
    def read(path):
        requested.append(path)
        if path is None:
            return json.dumps({"tree": [{"type": "blob", "path": valid},
                                         {"type": "blob", "path": "Practice/Complex_Analysis/paper.md"}], "truncated": False})
        if path.endswith(".json"):
            raise urllib.error.HTTPError(path, 404, "Not found", {}, None)
        assert path == valid
        return "积分 ANY_TEXTBOOK " * 20
    monkeypatch.setattr(course_sources, "_github_text", read)
    result = course_sources.load_github_materials("数学竞赛", "总结知识点", ("积分",), log=lambda *_: None)
    assert "ANY_TEXTBOOK" in result and requested[-1] == valid


def test_github_failure_uses_local_offline_material_without_blocking(tmp_path, monkeypatch):
    monkeypatch.delenv("COURSE_SKILL_LIBRARY", raising=False)
    monkeypatch.setattr(course_sources, "library_root", lambda: tmp_path)
    material(tmp_path, "Course", "Complex_Analysis", "notes.md", "复数 OFFLINE_TEXT " * 20)
    def offline(path):
        raise OSError("network unavailable")
    monkeypatch.setattr(course_sources, "_github_text", offline)
    logs = []
    result = course_sources.load_course_materials("复变函数", "总结知识点", ("复数",), log=logs.append)
    assert "OFFLINE_TEXT" in result
    assert any("network unavailable" in message for message in logs)


def test_github_plain_link_or_failed_body_is_not_reported_as_read(monkeypatch):
    path = "Course/Complex_Analysis/notes.md"
    def read(name):
        if name.endswith("index.json"):
            return json.dumps({"items": [{"path": path}]})
        raise OSError("body failed")
    monkeypatch.setattr(course_sources, "_github_text", read)
    logs = []
    assert course_sources.load_github_materials("复变函数", "总结知识点", ("复数",), log=logs.append) == ""
    assert not any("已从 GitHub" in message for message in logs)


def test_github_fetch_is_anonymous_bounded_and_cached_only_in_memory(monkeypatch):
    requests = []
    class Response:
        url = course_sources.LIBRARY_RAW + "Course/Complex_Analysis/notes.md"
        headers = {"Content-Type": "text/plain; charset=utf-8"}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            assert limit == 2_000_001
            return "复数 ONLINE_TEXT".encode("utf-8")
    def open_url(request, timeout):
        assert timeout == 10 and not request.has_header("Authorization")
        requests.append(request.full_url)
        return Response()
    monkeypatch.setattr(course_sources.urllib.request, "urlopen", open_url)
    now = [1000]
    monkeypatch.setattr(course_sources.time, "monotonic", lambda: now[0])
    course_sources._github_fetch.cache_clear()
    try:
        assert "ONLINE_TEXT" in course_sources._github_text("Course/Complex_Analysis/notes.md")
        course_sources._github_text("Course/Complex_Analysis/notes.md")
        assert len(requests) == 1
        now[0] += 301
        course_sources._github_text("Course/Complex_Analysis/notes.md")
        assert len(requests) == 2
        Response.headers = {"Content-Type": "text/html"}
        with pytest.raises(ValueError, match="网页"):
            course_sources._github_text("Course/Complex_Analysis/login.md")
    finally:
        course_sources._github_fetch.cache_clear()



def test_online_library_reads_create_no_project_material_files(tmp_path, monkeypatch):
    """Exercise the real HTTP reader while prohibiting filesystem writes by the retrieval path."""
    import io
    monkeypatch.delenv("COURSE_SKILL_LIBRARY", raising=False)
    monkeypatch.setattr(course_sources, "ROOT", tmp_path)
    path = "Course/Complex_Analysis/notes.md"
    class Response(io.BytesIO):
        headers = {"Content-Type": "text/plain"}
        def __init__(self, url, content):
            super().__init__(content.encode("utf-8"))
            self.url = url
    def open_url(request, timeout):
        body = (json.dumps({"items": [{"path": path, "title": "复数"}]})
                if request.full_url.endswith("/index.json") else "复数 IN_MEMORY_ONLY " * 20)
        return Response(request.full_url, body)
    def no_write(*args, **kwargs):
        pytest.fail("Online retrieval attempted a filesystem write")
    monkeypatch.setattr(course_sources.urllib.request, "urlopen", open_url)
    monkeypatch.setattr(Path, "write_text", no_write)
    monkeypatch.setattr(Path, "write_bytes", no_write)
    monkeypatch.setattr(course_sources, "_load_local_materials", lambda *a, **k: pytest.fail("Local fallback unnecessary"))
    course_sources._github_fetch.cache_clear()
    try:
        text = course_sources.load_course_materials("复变函数", "总结知识点", ("复数",), log=lambda *_: None)
        assert "IN_MEMORY_ONLY" in text and list(tmp_path.iterdir()) == []
    finally:
        course_sources._github_fetch.cache_clear()


@pytest.mark.parametrize("online", [False, True])
def test_textbook_modules_skip_archives_and_cover_distinct_sections(tmp_path, monkeypatch, online):
    prefix = "Course/Mathematics_Competition"
    records, bodies = [], {}
    for section in range(1, 11):
        for part in (1, 2):
            path = f"{prefix}/Textbook/section_{section:02}_{part}.md"
            records.append({"path": path, "title": f"极限主题 {section}",
                            "kind": "textbook_section", "modules": ["01_limit"],
                            "volume": 1, "chapter": 1, "section": section, "part": part})
            bodies[path] = f"极限 SECTION_{section:02} 内容。" * 120
    other = f"{prefix}/Textbook/derivatives.md"
    records.append({"path": other, "title": "极限 极限 极限", "kind": "textbook_section",
                    "modules": ["02_diff1"]})
    bodies[other] = "极限 WRONG_MODULE " * 120
    archive = f"{prefix}/Whole_Book.md"
    index = json.dumps({"items": records, "originals": [{"path": archive}]})
    requested = []
    def read(path):
        requested.append(path)
        return index if path.endswith("index.json") else bodies[path]
    if online:
        monkeypatch.setattr(course_sources, "_github_text", read)
        result = course_sources.load_github_materials(
            "数学竞赛", "总结知识点", ("极限",), chapter="模块一：极限与连续", log=lambda *_: None)
        assert other not in requested and archive not in requested
        assert len(requested) == 13  # one index, twelve bounded body reads
    else:
        for path, body in bodies.items():
            target = tmp_path / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        (tmp_path / prefix / "index.json").write_text(index, encoding="utf-8")
        (tmp_path / archive).write_text("极限 ARCHIVED_BOOK " * 120, encoding="utf-8")
        result = course_sources.load_course_materials(
            "数学竞赛", "总结知识点", ("极限",), root=tmp_path,
            chapter="模块一：极限与连续", log=lambda *_: None)
    assert "WRONG_MODULE" not in result and "ARCHIVED_BOOK" not in result
    assert all(f"SECTION_{number:02}" in result for number in range(1, 11))
    assert "教材目录" in result and len(result) < 18000


def test_explicit_module_handles_ocr_synonyms_without_false_body_claims(monkeypatch):
    path = "Course/Complex_Analysis/Textbook/cauchy.md"
    def read(name):
        if name.endswith("index.json"):
            return json.dumps({"items": [{"path": path, "title": "Cauchy theorem",
                "modules": ["03_complex_integration"], "kind": "source_text"}]})
        return "Cauchy contour formula CONTENT_FROM_MATCHED_SECTION " * 10
    monkeypatch.setattr(course_sources, "_github_text", read)
    result = course_sources.load_github_materials("复变函数", "总结知识点", ("复积分", "柯西"),
        chapter="模块三：复变函数的积分", log=lambda *_: None)
    assert "CONTENT_FROM_MATCHED_SECTION" in result
    def failed(name):
        if name.endswith("index.json"):
            return read(name)
        raise OSError("unavailable")
    monkeypatch.setattr(course_sources, "_github_text", failed)
    assert course_sources.load_github_materials("复变函数", "总结知识点", ("柯西",),
        chapter="模块三：复变函数的积分", log=lambda *_: None) == ""


def test_local_unindexed_materials_still_search_body_after_twelve_files(tmp_path):
    for number in range(14):
        material(tmp_path, "Course", "Complex_Analysis", f"{number:02}.md",
                 "无关正文" * 30 if number < 13 else "复数 UNINDEXED_MATCH " * 30)
    result = course_sources.load_course_materials("复变函数", "总结知识点", ("复数",),
        root=tmp_path, chapter="模块一：复数与复变函数", log=lambda *_: None)
    assert "UNINDEXED_MATCH" in result


def test_textbook_chapter_is_read_before_unreviewed_lecture_batches(monkeypatch):
    prefix = "Course/Complex_Analysis"
    records = [{"path": f"{prefix}/Lectures/{n:02}.md", "title": "复数 " * 6,
                "kind": "source_text", "modules": ["01_complex_numbers"]} for n in range(12)]
    chapter = {"path": f"{prefix}/Textbook/01_Complex_Numbers/chapter.md", "title": "复数",
               "kind": "textbook_chapter", "modules": ["01_complex_numbers"]}
    clean = {"path": f"{prefix}/Notes/numbers.md", "title": "复数",
             "kind": "cleaned_notes", "modules": ["01_complex_numbers"]}
    records.extend([chapter, clean])
    def read(path):
        if path.endswith("index.json"):
            return json.dumps({"items": records})
        marker = "CLEAN_NOTES" if path == clean["path"] else "CHAPTER_TEXT" if path == chapter["path"] else "LECTURE_OCR"
        return ("复数 " + marker + " ") * 300
    monkeypatch.setattr(course_sources, "_github_text", read)
    text = course_sources.load_github_materials("复变函数", "总结知识点", ("复数",),
        chapter="模块一：复数与复变函数", log=lambda *_: None)
    assert text.index("CLEAN_NOTES") < text.index("CHAPTER_TEXT") < text.index("LECTURE_OCR")


def test_official_fallback_uses_temporary_workspace_and_remote_open_bank(monkeypatch):
    from adapters import problem_sources
    from types import SimpleNamespace
    workspaces, requests = [], []
    def excerpts(keywords, cache_dir, log):
        assert not cache_dir.resolve().is_relative_to(problem_sources.ROOT.resolve())
        workspaces.append(cache_dir)
        (cache_dir / "transient-ocr.txt").write_text("temporary extracted content", encoding="utf-8")
        return []
    def read(path):
        assert path.startswith("Practice/Mathematics_Competition/Open_Problems/")
        requests.append(path)
        return json.dumps({"problems": [{"id": "REMOTE", "modules": ["模块一：极限与连续"],
                          "problem": "REMOTE_OPEN_PROBLEM", "source": "https://example.test/",
                          "license": "CC BY", "attribution": "author", "changes": "translation"}]})
    monkeypatch.setattr(problem_sources, "source_reader", lambda: SimpleNamespace(excerpts=excerpts))
    monkeypatch.setattr(problem_sources, "_github_text", read)
    result = problem_sources.load_practice_sources("模块一：极限与连续", ("极限",), log=lambda *_: None)
    assert "REMOTE_OPEN_PROBLEM" in result and len(requests) == 2
    assert workspaces and all(not path.exists() for path in workspaces)


@pytest.mark.parametrize("online", [False, True])
@pytest.mark.parametrize("subject", ["数学竞赛", "复变函数"])
def test_chapter_practice_reads_exercises_paired_answers_and_matching_exam_parts(
        tmp_path, monkeypatch, online, subject):
    chapter = next(iter(skill_rules.SUBJECT_MODULES[subject]))
    module = course_sources._module_key(subject, chapter)
    prefix = "Practice/" + skill_rules.SUBJECT_DIRS[subject]
    records, bodies = [], {}
    for number in range(14):
        path = f"{prefix}/Exercises/{number:02}.md"
        records.append({"path": path, "kind": "exercise", "role": "Questions",
                        "title": "章节题", "modules": [module]})
        bodies[path] = f"CHAPTER_EXERCISE_{number:02} 正文内容。" * 20
    answers = prefix + "/Answers/00.md"
    records[0]["paired_paths"] = [answers, "Practice/Other_Subject/private.md"]
    records.append({"path": answers, "kind": "exercise", "role": "Solutions",
                    "modules": [module]})
    bodies[answers] = "MATCHING_EXERCISE_ANSWER 本章解题过程。" * 20
    exam = prefix + "/Exams/paper.md"
    exam_answer = prefix + "/Exams/answers.md"
    for path, role in ((exam, "Questions"), (exam_answer, "Solutions")):
        records.append({"path": path, "kind": "past_paper", "role": role, "modules": [module],
                        "paired_paths": [exam_answer] if path == exam else [exam],
                        "topic_spans": [{"label": "第一题", "lines": [2, 2], "modules": [module]},
                                        {"label": "第二题", "lines": [3, 3], "modules": ["other"]}]})
        bodies[path] = "# 完整原卷\n" + (role + "_MATCHING_PAST_PAPER ") * 20 + "\nUNRELATED_EXAM_QUESTION"
    wrong = prefix + "/Exercises/another_module.md"
    records.append({"path": wrong, "kind": "exercise", "modules": ["other"]})
    bodies[wrong] = "WRONG_MODULE " * 20
    catalog = prefix + "/Chapters/" + module + ".md"
    bodies[catalog] = "CATALOG_LINKS_ONLY " * 30
    index = json.dumps({"items": records})
    requested = []
    if online:
        def read(path):
            requested.append(path)
            return index if path.endswith("/index.json") else bodies[path]
        monkeypatch.setattr(course_sources, "_github_text", read)
        text = course_sources.load_github_materials(
            subject, "练习", ("章节",), chapter=chapter, log=lambda *_: None)
        assert all(path.startswith(prefix + "/") for path in requested)
        assert wrong not in requested and catalog not in requested
    else:
        for path, body in bodies.items():
            target = tmp_path / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        (tmp_path / prefix / "index.json").write_text(index, encoding="utf-8")
        text = course_sources.load_course_materials(
            subject, "练习", ("章节",), root=tmp_path, chapter=chapter, log=lambda *_: None)
    assert "CHAPTER_EXERCISE_00" in text and "MATCHING_EXERCISE_ANSWER" in text
    assert "Questions_MATCHING_PAST_PAPER" in text and "Solutions_MATCHING_PAST_PAPER" in text
    assert "UNRELATED_EXAM_QUESTION" not in text and "WRONG_MODULE" not in text
    assert "CATALOG_LINKS_ONLY" not in text


@pytest.mark.parametrize("spans", [
    [{"modules": ["other"], "lines": [1, 1]}],
    [{"modules": ["module"], "lines": [0, 1]}],
    [{"modules": ["module"], "lines": [1, 99]}],
    [{"modules": ["module"], "lines": [True, 1]}],
    [{"modules": ["module"], "lines": "1:1"}],
    ["invalid"],
    "invalid",
])
def test_invalid_or_unmatched_question_spans_do_not_leak_whole_exam(spans):
    item = {"modules": ["module"], "topic_spans": spans}
    assert course_sources._material_excerpt("极限 UNRELATED_CONTENT", item, ("极限",), 1000, "module") == ""

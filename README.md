# Course_Skill

Course_Skill is a desktop study helper. Pick a subject and a topic, and it
asks an AI to write either **study notes** or **practice papers with full
solutions**. You get the result as a Word, PDF, Markdown, or HTML file.

It currently covers two subjects:

- **数学竞赛**: Chinese college math competition, non-math-major track (非数学 A 类)
- **复变函数**: complex analysis, plus Fourier and Laplace transforms

It's built for Windows and the interface is in Chinese. This README gives the
Chinese button names along with what they mean.

## Getting started

You'll need:

- **Python 3.10 or newer**
- **Edge or Chrome**
- **One AI service**: ChatGPT (website login, Codex CLI, or API key), DeepSeek
  (API key), or Doubao 豆包 (API key)

The repository doesn't include any API keys or textbooks. You bring your own.

**1. Install and launch.** Open a terminal in the project folder (the one with
`main.py`) and run:

```sh
python -m pip install -r requirements.txt
python main.py
```

If you cloned the source code instead of downloading a release, build the
interface once first. This needs **Node.js 22+**:

```sh
npm --prefix frontend ci
npm --prefix frontend run build
```

Your browser opens automatically. Keep the terminal open while you work, and
press **Ctrl+C** in it to quit.

**2. Choose what to make.**

- **科目** (subject): 数学竞赛 or 复变函数
- **知识点总结** (study notes) or **题目练习** (practice papers)
- A module (topic), or **全部模块** (all modules)
- **输出格式** (output format): Word, PDF, MD, or HTML

**3. Set up your AI.** Click **设置** (settings), pick a service, and fill in
what it asks for. See [Choosing an AI service](#choosing-an-ai-service) below.

**4. Click 一键配置环境 (one-click setup).** Do this the first time, and again
whenever you switch AI service or output format. It installs whatever's missing
and runs a quick test. If it asks you to log in to something, the instructions
show up in the **详细日志** (detailed log) panel.

**5. Click 开始生成 (start).** The finished file opens on its own when it's ready.
You can find all your files in the `output/` folder, or click **输出文件夹**.
When you use an API, the number of tokens used is shown under each finished
file, so you can estimate the cost. Older files are never overwritten. A second run gets saved as
`practice_2.pdf`, then `practice_3.pdf`, and so on.

You can close or refresh the browser tab and the work keeps going. Only one task
runs at a time, and you can't pause or cancel one. To stop everything, press **Ctrl+C**
in the terminal.

## Choosing an AI service

| Service | How to connect | What you need |
| --- | --- | --- |
| ChatGPT | GUI, CLI, or API | A ChatGPT login, a Codex CLI login, or an OpenAI API key |
| DeepSeek | API | A DeepSeek API key |
| Doubao 豆包 | API | A Volcengine Ark API key |

You only need to set up one.

**API.** Paste your key and click **读取模型** (load models) to choose from your
account's models. If nothing comes back, type the model ID yourself. Doubao
also accepts endpoint IDs like `ep-...`. Paste just the key, with no quotes and
no `Bearer` in front. Your key is held in memory while the app is running. It
isn't saved to disk, so you'll need to enter it again after a restart. You pay
your provider for usage as usual.

**ChatGPT CLI.** Click **一键配置环境**, which can install Node.js and Codex CLI
for you on Windows. Then log in once from a terminal:

```sh
codex login
```

**ChatGPT GUI.** This option drives the ChatGPT website directly. Click
**一键配置环境** to get the browser ready. When you start generating, a ChatGPT
window opens. Log in there and choose your model. The window stays open
afterwards, so close it when you're finished. Your login is remembered, but if
ChatGPT changes its website, this mode may stop working until the app is
updated.

## What you get

### Study notes (知识点总结)

Notes for one module cover the definitions, formulas, the conditions they need,
theorems, methods, and common mistakes. They're kept tight. Each topic gets a
short heading, the most important 6–8 formulas are boxed, and every module ends
with a list of 7–10 traps to watch out for. The **comprehensive** module ties
all the other modules together. It takes more AI calls, so it's slower and
costs more.

### Practice papers (题目练习)

Each run produces **two papers**, then the answers and worked solutions.

| Subject | Each paper contains |
| --- | --- |
| 数学竞赛 | 5 fill-in-the-blank + 5 full-solution questions |
| 复变函数 | 5 fill-in-the-blank + 5 multiple-choice + 4 full-solution questions |

The app remembers every question it has given you for each module. These are
stored in `local_practice/`. A new question that's too close to an old one gets
rejected. Same goes for one that only swaps a few numbers or variable names.
When that happens, or when a paper comes back in the wrong layout, the app asks
the AI to try again, up to two more times. Each retry is another AI call. If the third
attempt still has repeats, a small box appears in the progress panel asking
whether to keep that paper anyway (保留) or throw it away (放弃).

To add an older paper to this history so future papers avoid its questions:

```sh
python skills/Common/scripts/check_practice.py "paper.md" --chapter "模块一：极限与连续" --record
```

> **Always check the maths yourself.** The app makes sure the papers have the
> right structure, but it can't tell whether an answer is correct or a question
> is as hard as it should be.

### Modules

**数学竞赛** has 7 modules:

1. Limits and continuity
2. Differentiation (one variable)
3. Integration (one variable)
4. Differentiation (several variables)
5. Multiple, line, and surface integrals
6. Series and differential equations
7. Comprehensive: mixing topics from all modules

**复变函数** has 8 modules: complex numbers and functions, analytic functions,
complex integration, series, residues, Fourier transforms, Laplace transforms,
and a comprehensive review.

**全部模块** (all modules) runs the modules one after another. It makes one
document per module and skips the comprehensive module, which you have to pick
on its own. The one exception is 数学竞赛 practice papers, where the
comprehensive module is included.

The progress bar shows which step you're on. It isn't a time estimate. It will
often sit still while the AI is writing.

## Output formats

| Format | Notes | Needs |
| --- | --- | --- |
| Word | Equations can be edited in Word | Pandoc |
| PDF | Made through your browser by default | Edge or Chrome |
| MD | Plain Markdown, easy to edit | Nothing extra |
| HTML | Opens in any browser, works offline | Edge or Chrome |

**一键配置环境** installs any of these that are missing. There's also an optional
**LaTeX（专业排版）** PDF mode for professional typesetting, but you don't need
LaTeX for normal PDFs.

Documents use 14pt Songti for body text, bold Heiti for headings, and indented
paragraphs. If a formula won't render, the app asks the AI to fix that formula
only, up to twice. If export still fails, the Markdown file is kept so nothing
is lost. You can export it again without making another AI request:

```sh
python adapters/pdf_export.py "output/notes.md"
```

## Textbooks and reference material (optional)

Course_Skill works fine with no textbook at all. If you give it more to work
with, here's the order it uses things:

1. **Your own textbook PDFs.** Click **教材文件夹** (textbook folder) and drop
   PDFs into `local_textbook/`. The app sends the AI the relevant pages, not the
   whole book. Scanned books get OCR'd on Windows. The first run on a big book
   can take several minutes, but the result is cached, so you only wait once.
   If OCR fails, add the Chinese language pack in Windows Settings.
2. **The shared course library.** The app pulls short, relevant excerpts from the
   public [Assistant_course](https://github.com/Lyric-zephyr/Assistant_course)
   repository automatically. You don't need to download it. If GitHub can't be
   reached, it looks for an `Assistant_course/` folder next to this project.
   You can also point `COURSE_SKILL_LIBRARY` at a local copy.
3. **The AI's own knowledge** fills in whatever's left.

Practice papers draw first on past exam papers and exercises in the course
library, then on public sources such as past competition papers and MIT
OpenCourseWare. If the AI couldn't find any real source material, the paper is
marked as **simulated practice** (模拟练习). See the
[source-access notes](skills/Mathematics_Competition/references/source_access.md)
for details.

To clear the textbook cache, delete `local_textbook/.ocr-cache/`. To re-read just
one book:

```sh
python skills/Common/scripts/extract_pdf.py "textbook.pdf" --refresh --output textbook.txt
```

## Troubleshooting

| Problem | Try this |
| --- | --- |
| Something says a tool is missing | Choose your AI and output format, then click **一键配置环境** |
| Codex CLI isn't logged in | Run `codex login`, then run setup again |
| No models show up | Check your key and provider. You can also type the model ID by hand |
| The API refuses the request | Check your key, your account balance, and that your account can use that model |
| An error mentions `latin-1` or bad characters in the key | Copy the key again and paste only the key, with no label, quotes, or `Bearer` |
| ChatGPT GUI gets stuck | Look at the ChatGPT window. You may need to log in or complete a verification |
| A textbook can't be read | Let OCR finish. If it fails, install Chinese OCR in Windows language settings |
| A formula won't render | The error tells you the line number. Fix it in the `.md` file and export again |
| Export fails because the file is in use | Close the file in Word or your PDF viewer and try again |
| A practice paper keeps failing its checks | Look at the Markdown file that was saved and fix it by hand |

## Customizing

Everything the AI is told to do is written in plain Markdown files, and you can
edit them. Your changes apply the next time you generate something.

| File | Controls |
| --- | --- |
| [skills/Common/SKILL.md](skills/Common/SKILL.md) | Rules for both subjects: formatting, source priority, notes and practice |
| [Mathematics_Competition/SKILL.md](skills/Mathematics_Competition/SKILL.md) | Competition scope, question types, difficulty |
| [Complex_Analysis/SKILL.md](skills/Complex_Analysis/SKILL.md) | Complex analysis modules and paper layout |
| [knowledge_summary.md](skills/Common/references/knowledge_summary.md) | How study notes are structured |
| [problem_set.md](skills/Mathematics_Competition/references/problem_set.md) | How practice papers are structured |
| [references/modules/](skills/Mathematics_Competition/references/modules/) | What each competition module covers |
| [document.html](skills/Common/assets/web/document.html) | PDF and HTML styling |
| [template.tex](skills/Common/assets/template.tex) | LaTeX PDF styling |

<details>
<summary><strong>Advanced: command line and environment variables</strong></summary>

You can set API keys with environment variables instead of typing them into the
app:

| Service | Key | Model | Base URL |
| --- | --- | --- | --- |
| ChatGPT | `OPENAI_API_KEY` | `OPENAI_MODEL` | `OPENAI_BASE_URL` |
| DeepSeek | `DEEPSEEK_API_KEY` | `DEEPSEEK_MODEL` | `DEEPSEEK_BASE_URL` |
| Doubao | `ARK_API_KEY` | `ARK_MODEL` | `ARK_BASE_URL` |

Generate a document without the interface:

```sh
python adapters/run.py "Focus on common mistakes" output/notes --provider dsh --api-model YOUR_MODEL --task-mode summary --chapter "模块一：极限与连续" --output-format pdf
```

Set `--provider` to `codex` for ChatGPT, `dsh` for DeepSeek, or `doubao` for
Doubao. Options include `--output-format word|pdf|md|html`,
`--task-mode summary|practice`, and `--timeout SECONDS` (default 1200).

Default model IDs, and the list of Codex CLI models in the settings panel, are
kept in [models.json](models.json). Edit that file when providers release new
models.

If the app can't find tools you installed somewhere unusual, tell it where they
are before launching:

```powershell
$env:MATH_COMP_BROWSER = "D:\Tools\Browser\chrome.exe"
$env:MATH_COMP_PANDOC  = "D:\Tools\Pandoc\pandoc.exe"
$env:MATH_COMP_TEX_BIN = "D:\Tools\MiKTeX\miktex\bin\x64"
python main.py
```

Other launch options:

- `python main.py --no-browser` starts the server without opening a browser.
- `python adapters/pdf_export.py "output/notes.md" --engine latex` exports a PDF
  with LaTeX.
- `python skills/Mathematics_Competition/scripts/scrape_cmathc.py --refresh`
  rebuilds the index of past competition papers. Add `--download-all` to try
  downloading every one of them.

</details>

## For developers

The interface is built with React and TypeScript in `frontend/`, and the backend
uses FastAPI. Both run only on your own computer. After changing the frontend,
run `npm --prefix frontend run build` and refresh the page. If a `.venv` folder
exists, `main.py` uses it automatically.

The server only listens on `127.0.0.1` and requires a one-time login link, which
is the link that opens in your browser. Don't share that link.

```text
Course_Skill/
├── main.py           # Start here
├── frontend/         # Web interface (React)
├── launcher/         # Backend server and task runner
├── adapters/         # AI connections, setup, and file export
├── skills/           # The rules given to the AI, per subject
├── local_textbook/   # Your textbook PDFs (not uploaded to Git)
├── local_practice/   # Question history (not uploaded to Git)
├── local_problems/   # Cache for the past-paper index (not uploaded to Git)
└── output/           # Your generated documents
```

To build a release ZIP with the interface already built, run
`python scripts/package_release.py`. See [CONTRIBUTING.md](CONTRIBUTING.md)
for how to contribute. Issues and pull requests are welcome in English or
Chinese. To report a security problem, see [SECURITY.md](SECURITY.md).

## License

The project's own code, rules, and templates are under the [MIT License](LICENSE).
Third-party software and materials keep their own licenses. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

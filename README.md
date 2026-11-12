# Course_Skill

A desktop study workspace with a subject selector for **数学竞赛 (Mathematics
Competition)** and **复变函数 (Complex Analysis)**. Mathematics Competition is
fully available; Complex Analysis currently provides a UI entry only, with
generation disabled until its subject rules and backend are connected.
Generate study notes or practice papers with your chosen AI, then save the
result as **Word, PDF, Markdown, or HTML**.

Built primarily for Windows. The interface and generated study materials are
mainly in Chinese; this README explains the Chinese button labels as you go.

## Quick start

You need **Python 3.10+**, a modern browser, and access to one supported AI service.
The default interface is a light Chinese web workspace served only on this computer.
Tkinter is needed only for the legacy interface.
No API key, textbook, or browser session is included in the repository.

1. Download the complete repository and extract it, or clone it with Git.
2. Open a terminal in the folder containing `main.py`. For a source checkout,
   install **Node.js 22+**, then install dependencies, build the frontend, and start:

   ```sh
   python -m pip install -r requirements.txt
   npm --prefix frontend ci
   npm --prefix frontend run build
   python main.py
   ```

   The launcher opens your browser after the server is ready. Release packages include
   the built frontend, so they do not need Node.js or the two `npm` commands.

3. Under **科目 (Subject)**, select **数学竞赛 (Mathematics Competition)**.
   Choose **知识点总结** for study notes or **题目练习** for questions and solutions,
   then choose a module. **复变函数 (Complex Analysis)** is a UI preview only.
4. Open **设置** to choose an AI service and running method from the table below. For **API**,
   enter your key and model ID. Select **Word**, **PDF**, **MD**, or **HTML** under
   **输出格式**.
5. **Click 一键配置环境 (One-click setup) first.** The app installs missing
   tools where supported, checks the selected setup, and exports a sample.
   Follow any login instructions in the **详细日志** panel.
6. Click **开始生成** to generate your document.

Files are saved in `output/` and open automatically when generation succeeds.
Use **输出文件夹 (Open output folder)** to find them later.

**No textbook is required.** If you provide one, relevant excerpts take
priority. Otherwise, the AI generates notes from its own mathematics knowledge.

## Web workspace and development

The React/TypeScript frontend and FastAPI backend are separate. Production assets
are served by the same local server; no cloud deployment or Node.js runtime is
needed for everyday use. Source checkouts require Node.js 22+ to build once:

```sh
npm --prefix frontend ci
npm --prefix frontend run build
python main.py
```

After frontend changes, rebuild and refresh the page. For frontend-only work,
`npm --prefix frontend run dev` serves Vite; it intentionally has no production
API credentials or cross-origin API proxy. Use the built interface for integrated
work. Missing assets produce explicit build instructions instead of installing
Node.js automatically. Backend dependencies are in `requirements.txt`.

The server chooses an available port on `127.0.0.1` and opens an authenticated
startup URL. The token is exchanged for an HttpOnly, SameSite cookie; the UI removes
the startup query from its displayed address. Do not share the startup URL.
Host, Origin and session authentication are checked on API requests. Files can
only be opened using server-issued IDs or fixed resource names.

Refreshing, closing, or reopening the page does not interrupt a task. Keep the
launcher terminal running; press Ctrl+C there to stop the service and its workers.
The dedicated ChatGPT login browser remains open. Only one generation, setup, or
source-index task runs at a time. There is no pause, cancellation, historical task
browser, or resume after a backend restart. The current task, bounded logs and
result files remain visible while the backend runs; all task snapshots remain in
server memory until shutdown. Ordinary preferences are saved in browser local
storage. API keys stay in backend memory, are never returned to the frontend,
and must be re-entered after a backend restart unless supplied by environment.

The task card contains module and format choices. **设置** opens the AI settings
drawer. The right panel shows actual stage progress, module statuses, results and
collapsible logs. Partial failures expand the logs. Successful files still open
automatically; result cards also offer **打开文件** and **所在文件夹**. Missing
output dependencies should be prepared with **一键配置环境**.

The old interface remains available during migration:

```sh
python main.py --legacy-ui
```

It shares the same generation and environment-setup service. It requires Tkinter.
`python main.py --no-browser` starts the web server without opening a browser.

To validate without AI calls:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend test
```

Browser tests use a temporary simulated backend, never your textbooks or keys.
On Windows they use installed Edge; on Linux they use Playwright Chromium.
Create a distributable source ZIP including built assets with
`python scripts/package_release.py`; it packages committed sources and the current
frontend build, excluding local study data. Commit source changes before packaging.

## Choose an AI service

| Service | Running methods | What you provide |
| --- | --- | --- |
| GPT (Codex) | GUI, CLI, API | Website login, Codex CLI login, or an API key and model ID |
| DeepSeek (DSH) | API | A DeepSeek API key and model ID |
| Doubao (豆包) | API | A Volcengine Ark API key and model or inference endpoint ID |

Only configure the method you intend to use. All supported methods work with
both tasks and all four output formats.

### API

Select **API**, enter your **API-Key**, then click **读取模型 (Read models)**.
Choose a model from the returned list or type its exact API model ID directly.
Doubao also accepts an inference endpoint ID such as `ep-...`.

The key authenticates your account; **its format does not identify a model**.
Reading models sends a request to the selected provider. If that provider does
not expose a compatible model-list endpoint, enter the ID manually. Availability
and generation permissions depend on your account.

GPT API starts with an empty model field unless you set `OPENAI_MODEL`.
API model IDs can differ from Codex CLI names. An API key and a model ID are
both required; website login does not replace API credentials.

Keys entered in the app stay in memory and are passed to the adapter through
its environment. They are not saved in project files or command-line arguments.
API charges depend on the provider and your account.
Paste only the actual key, without labels, quotes, or a `Bearer` prefix. Local
checks reject non-ASCII characters and embedded whitespace before textbook
extraction, preventing request-header encoding errors after a long OCR run.

### GPT CLI

Choose **GPT (Codex) → CLI**, then click **一键配置环境**. On Windows, setup can
install missing Node.js and Codex CLI. Complete the first login in a terminal:

```sh
codex login
```

Select a CLI model your account supports, then return to the app. For manual
installation, see the [official Codex documentation](https://developers.openai.com/codex/noninteractive/).

### GPT GUI

Choose **GPT (Codex) → GUI** and click **一键配置环境** to prepare Playwright and
Edge/Chrome. Generation opens a dedicated ChatGPT browser window. Sign in,
complete any verification, and choose the model on the website.

The app waits for the page to be ready before submitting the prompt. The browser
stays open after success, failure, or timeout; close it yourself when finished.
If submission status is uncertain, check that window before retrying.

Login sessions are stored outside the repository, under
`%LOCALAPPDATA%/MathCompSkill/browser/` on Windows. Website layout changes can
affect automation. DeepSeek and Doubao use API only.

## Tasks and modules

| Task | Result | Reference behavior |
| --- | --- | --- |
| SUMMARY — 知识点总结 | Formulas, theorems, conditions, common mistakes, and extensions | Uses optional textbooks or the AI's own knowledge; does not retrieve past papers or question banks |
| PRACTICE — 题目练习 | Two practice papers followed by answers and detailed solutions | Uses available past-paper references, a small bundled open collection, and optional textbooks |

Practice targets **non-mathematics A (非数学 A 类)**. Each paper contains
**five fill-in questions and five full-solution questions**, numbered **1–10
independently**. Both papers appear before the answer section; solutions are
grouped under separate first-paper and second-paper headings.

The app checks question counts, numbering, and section structure. This check
does not verify mathematical correctness or guarantee competition difficulty.

Practice also keeps a per-module question history in `local_practice/`, shared
across AI providers, running methods, and output formats. New papers are checked
against all recorded questions and against each other. Exact repeats, changes
limited to numbers or variable names, and highly similar text trigger up to two
additional generation requests, which can incur additional API charges. If all
three attempts fail the check, export stops. Semantic equivalence cannot be
guaranteed by text checks alone; the Skill also requires different problem designs.

Keep this ignored local history to preserve avoidance across restarts. It stores
question statements, not textbook OCR results, and records accepted questions
even if subsequent document conversion fails. Earlier Markdown papers can be
registered with:

```sh
python skills/math-comp-prep/scripts/check_practice.py "paper.md" --chapter "模块一：极限与连续" --record
```

Overwritten or unrecorded past papers cannot be reconstructed automatically.

| Module | Topic |
| --- | --- |
| 1 | Limits and continuity |
| 2 | Single-variable differentiation |
| 3 | Single-variable integration |
| 4 | Multivariable differentiation |
| 5 | Multiple, line, and surface integrals |
| 6 | Series and ordinary differential equations |
| 7 | Comprehensive practice and connections across modules |

Choose **全部模块 (All modules)** to generate **six summaries** (modules 1–6)
or **seven practice documents** (modules 1–7), depending on the task.
The current queue processes modules one at a time.

The progress bar shows the whole workflow as a percentage: environment checks
(0–5%), textbook reading (5–25%), and the selected modules (25–100%). Textbook
progress follows pages inspected/OCR batches; generation advances when summary
parts finish, practice validation finishes, and files are exported. During a
single AI request it stays at the current stage: this is workflow progress,
not a token count or a time estimate. Retries do not move the bar backward.
At 100%, the queue has been processed; check the success/failure counts in the log.

Summary priorities are **complete coverage first**, then **concise explanations
with clear emphasis on key points**. Cover definitions, formulas, conditions,
theorems, methods, extensions, and common mistakes. Present formulas, conditions,
and key results under natural subheadings, with only brief necessary explanations.
Use short paragraphs rather than bullet lists or mechanically numbered items.
Avoid restating formulas in prose or expanding unnecessary derivations; preserve
essential content and emphasize key points.
Merge redundant formulas and omit unnecessary intermediate expressions, aiming
for about 20% fewer formulas without losing essential coverage. Usually highlight
6–8 important formulas per module with boxes and bold the key statements.
There is no fixed word-count target or requirement to match a textbook's length.
Each module is generated in three parts—formulas, theorems, and extensions—then combined.
Only an unfinished part is retried once. Select module 7 separately for a complete
compilation of modules 1–6 plus connections between them; it keeps all six modules'
content rather than compressing it into a single short overview. This requires
more AI requests and may increase generation time and API charges. Coverage and
mathematical accuracy still depend on the model and should be reviewed.

## Output formats

| Format | Saved file | Tools used |
| --- | --- | --- |
| Word | `.docx`, with editable equations | Pandoc |
| PDF | `.pdf`; browser export is the default | Edge/Chrome, or optional Pandoc + XeLaTeX |
| MD | `.md`, ready for editing | No rendering tools |
| HTML | `.html`, with embedded math styles and fonts | Edge/Chrome during generation |

Successful generation saves **only the selected format**. Conversion files stay
in temporary folders. Generating the same task and module again replaces its
previous file in that format.

Formatted documents use **14pt Songti body text**, two-character paragraph
indents, bold Heiti headings, numbered subheadings, and bold key statements.
Body paragraphs after headings or equations also use two-character first-line
indents; standalone equations are centered without paragraph indentation.
Major headings use 16pt; only major sections enter the table of contents.
Practice paper and solution headings are centered. Markdown appearance depends
on the viewer.

Browser PDF export scales overwide formulas individually to keep body text at
its intended size. KaTeX, Marked, and math fonts are bundled locally; rendering
does not need a CDN. AI generation still needs a network connection.

Runs of underscores inside math are automatically converted to valid fill-in
lines. If browser PDF/HTML export still reports invalid formulas, generation
automatically asks the selected AI to repair only those formulas and retries
export up to twice, without regenerating the questions or the entire document.
These repair requests may incur API charges. Browser startup/printing failures
are also retried once. If recovery fails, Markdown remains available for editing
and re-export; no unlimited retry loop is used.

## What one-click setup handles

The button configures the **currently selected AI method and output format**:

- Installs missing Python helpers and checks the output with a sample document.
- For GPT GUI, prepares Playwright and checks the automation browser.
- For GPT CLI, installs missing CLI tools on Windows and checks login status.
- For API, checks that credentials, a model, and a supported service URL are
  configured. Actual authentication and generation permissions are checked by
  the provider when requests are made.
- For Word, installs missing Pandoc on Windows.
- For browser PDF or HTML, detects Edge/Chrome and can install missing Edge on
  Windows.
- For **LaTeX（专业排版）**, installs missing Pandoc/MiKTeX on Windows, enables
  package installation, checks updates, and tests compilation.

**Default PDF export needs no MiKTeX, Perl, Pandoc, or LaTeX.** Choose LaTeX
only when you want that typesetting workflow.

Automatic Windows system-tool installation uses **WinGet (App Installer)** and
needs internet access. Login, API credentials, and any operating-system approval
prompts remain manual. Other operating systems require missing system tools to
be installed manually. AI and output setup report their results separately.

## Optional textbooks and practice references

Click **教材文件夹 (Open textbook folder)** and place textbook PDFs in
`local_textbook/`. The reader works with user-provided PDFs across textbooks
and editions. Matching excerpts are sent to your chosen AI. On Windows, pages
without a text layer are automatically processed by the built-in OCR engine,
with page progress shown in the UI and log.

Successful recognition is saved locally in `local_textbook/.ocr-cache/`, which
is covered by the existing Git ignore rule. Later runs hash the current PDF
with SHA-256 and check the extractor/OCR script versions and PyMuPDF version;
unchanged files reuse their text without repeating extraction or OCR. Renaming
the same PDF does not invalidate its cache. Changed content, changed extraction
tools, or damaged/incomplete cache data cause recognition to run again. Password
and copy restrictions are checked before reading a cache. Only successful,
nonempty results are saved, using an atomic file replacement; failed cache
writes do not block the current run. Temporary page images are cleaned up.

Delete `local_textbook/.ocr-cache/` to clear all textbook memory, or force a
single textbook to be recognized again:

```sh
python skills/math-comp-prep/scripts/extract_pdf.py "textbook.pdf" --refresh --output textbook.txt
```

Use `--no-cache` to skip both cache reads and writes for that command.
Caches stay local. Force recognition again after fixing an OCR language/tool issue.
A large scanned book can take several minutes on its first run. OCR
requires an installed Windows recognition language. The AI may correct OCR
errors using context and mathematical consistency checks; material assumptions
must be identified, and unrecoverable passages are skipped. Such reconstruction
does not establish the exact original wording or guarantee mathematical accuracy.
On other systems, add a text layer with an OCR tool first.
Missing or irrelevant textbook content does not prevent knowledge summaries
from being generated.

In **PRACTICE** mode, **真题来源 (Past-paper sources)** opens a report covering
discovered sources from editions **1–17**. An indexed edition is not a claim
that every paper was downloaded or read successfully.

The reader checks robots rules, redirects, login responses, and PDF password
and copying restrictions. It reads permitted PDFs in memory by default.
`local_problems/` holds the source index and OCR cache; it is runtime data,
is recreated when needed, and is excluded from version control.

If no usable official text is available, the prompt requires the output to be
identified as unverified simulated practice. OCR can misread formulas. The app
also includes a small attributed selection of **three MathNet problems** and
**six MIT OCW problems**, rather than a complete competition bank.

See the [source-access notes](skills/math-comp-prep/references/source_access.md)
for source availability and retrieval behavior.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| A required tool cannot be found | Select your AI method and output format, then click **一键配置环境** |
| Codex CLI is installed but not signed in | Run `codex login`, then check setup again |
| The API model field is empty | Enter a key and click **读取模型**, or type the exact API model/endpoint ID |
| The model list cannot be read | Check the key and selected provider; enter the ID manually if listing is unsupported |
| An API call is rejected | Check the key, model access, endpoint, and account status with the provider |
| A `latin-1` or API-Key character error appears | Copy the real key from the provider again; remove labels, quotes, a `Bearer` prefix, or placeholder text. Do not change the encoding of the textbook or strip characters from the secret itself |
| GPT GUI does not continue | Complete login/verification in the retained window; website changes may require an adapter update |
| A textbook cannot be read | On Windows, let automatic OCR finish; if its language is unavailable, install Chinese OCR in Windows language settings. Elsewhere, OCR the PDF first. Summaries can also run without textbooks |
| A formula fails to render | Use the reported Markdown line to fix the saved source, then export it again |
| The output file is locked | Close the existing document in its viewer and retry export |
| A practice paper has the wrong structure | Review the retained Markdown; the app preserves it rather than exporting an invalid layout |

Transient browser failures are retried **once**, without another AI call.
If conversion still fails, Markdown is preserved so you can recover the content.
Re-export it without regenerating:

```sh
python adapters/pdf_export.py "output/notes.md"
```

Use complete formula syntax such as `\frac{a}{b}`; see
[KaTeX-supported syntax](https://katex.org/docs/supported.html). If you already
have a rendered HTML document, you can also open it in Edge/Chrome and use
**Ctrl+P → Save as PDF**.

## Customize the rules

GPT, DeepSeek, and Doubao share the same task and module rules.

| File or directory | Purpose |
| --- | --- |
| [SKILL.md](skills/math-comp-prep/SKILL.md) | Task routing and shared requirements |
| [knowledge_summary.md](skills/math-comp-prep/references/knowledge_summary.md) | Summary structure and formatting |
| [problem_set.md](skills/math-comp-prep/references/problem_set.md) | Practice structure and difficulty requirements |
| [references/modules/](skills/math-comp-prep/references/modules/) | Scope of each module |
| [document.html](skills/math-comp-prep/assets/web/document.html) | Browser PDF/HTML typography |
| [template.tex](skills/math-comp-prep/assets/template.tex) | XeLaTeX typography |
| [format_practice.lua](skills/math-comp-prep/scripts/format_practice.lua) | Practice layout for LaTeX export |
| [check_practice.py](skills/math-comp-prep/scripts/check_practice.py) | Check or register papers against per-module question history |

Rule changes affect new generations. Template changes affect newly exported
documents; existing PDFs keep their layout until exported again.

<details>
<summary><strong>Advanced: environment variables and command-line tools</strong></summary>

Run commands from the project folder. For API calls, you can set credentials
outside the app using these variables:

| Service | Key | Model override | Base URL override |
| --- | --- | --- | --- |
| GPT | `OPENAI_API_KEY` | `OPENAI_MODEL` | `OPENAI_BASE_URL` |
| DeepSeek | `DEEPSEEK_API_KEY` | `DEEPSEEK_MODEL` | `DEEPSEEK_BASE_URL` |
| Doubao | `ARK_API_KEY` | `ARK_MODEL` | `ARK_BASE_URL` |

Base URLs default to official provider endpoints. Example with shared summary
rules and a selected module:

```sh
python adapters/run_dsh.py "Focus on common mistakes" output/notes --run-mode API --api-model YOUR_MODEL --task-mode summary --chapter "模块一：极限与连续" --output-format pdf
```

Use `adapters/run_codex.py` for GPT or `adapters/run_doubao.py` for Doubao.
All adapters accept `--output-format word|pdf|md|html`, `--timeout SECONDS`
(default: 1200), and `--task-mode summary|practice` with `--chapter`.

To use the optional XeLaTeX exporter:

```sh
python adapters/pdf_export.py "output/notes.md" --engine latex
```

The app checks registry PATH entries and common tool locations on Windows.
For custom installations, set the actual paths before launching:

```powershell
$env:MATH_COMP_BROWSER = "D:\Tools\Browser\chrome.exe"
$env:MATH_COMP_PANDOC = "D:\Tools\Pandoc\pandoc.exe"
$env:MATH_COMP_TEX_BIN = "D:\Tools\MiKTeX\miktex\bin\x64"
python main.py
```

Replace these example paths with real locations. `MATH_COMP_XELATEX` can specify
an exact `xelatex.exe` path. The LaTeX template requires XeLaTeX; use it through
the exporter, which fills in the document content.

To refresh the past-paper source index:

```sh
python skills/math-comp-prep/scripts/scrape_cmathc.py --refresh
```

To attempt downloading every discovered, automatically accessible PDF from
editions 1–17:

```sh
python skills/math-comp-prep/scripts/scrape_cmathc.py --download-all
```

The report lists restricted, missing, and failed sources.

</details>

## Project layout

```text
Course_Skill/
├── main.py                  # Local web launcher; --legacy-ui for Tkinter
├── frontend/                # React UI; dist/ is generated by the build
├── launcher/                # Shared task service, FastAPI and legacy interface
├── adapters/                # AI integrations, environment setup, exporters
├── skills/math-comp-prep/   # Shared rules, scripts, templates, open references
├── local_textbook/          # Place textbook PDFs here; contents and OCR cache stay local
├── local_problems/          # Runtime reference cache; created when needed
├── local_practice/          # Per-module generated-question history; local only
└── output/                  # Generated documents
```

## Contributing

Bug reports, math-rule improvements, and pull requests are welcome in English
or Chinese. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup,
verification, and contribution guidelines. Optional Python helpers are listed
in [requirements.txt](requirements.txt); one-click setup remains the recommended
way to prepare your selected method and output format.

GitHub issue and pull request templates are included. GitHub Actions checks
Python syntax, bundled JSON, and CLI entry points on Windows and Linux without
calling AI services. Live accounts, GUI login, and document rendering require
separate checks.

Report vulnerabilities using [SECURITY.md](SECURITY.md).

## License

Original project code, rules, and templates use the [MIT License](LICENSE).
Third-party software and reference materials retain their own licenses, listed
in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

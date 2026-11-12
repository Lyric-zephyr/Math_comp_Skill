# Contributing to MATH COMP

Bug reports, documentation fixes, math-rule improvements, and small pull
requests are welcome. Please keep discussions respectful and changes focused.

## Local development

Use Python 3.10+ and Node.js 22+ for frontend development. Tkinter is optional
and required only for `python main.py --legacy-ui`. From the project root:

```sh
python -m venv .venv
```

Activate the environment before installing helpers or running the app:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```sh
# Linux / macOS
source .venv/bin/activate
```

The app's **一键配置环境 (One-click setup)** prepares the selected method and
format. To install the optional Python helpers manually:

```sh
python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
python main.py
```

System tools and AI login/API credentials are configured separately; see the
[README](README.md). Never commit credentials or browser sessions.

## Reporting a problem

Use the GitHub issue templates. Include your Python version, operating system,
AI service and method, output format, reproduction steps, and the relevant
sanitized log. For math errors, provide a minimal example and the correct result.
For security problems, follow [SECURITY.md](SECURITY.md).

Remove API keys, account details, private textbook content, and personal paths
before attaching logs or screenshots. Prefer a short original example over
uploading a complete textbook or competition paper.

## Making a change

- Preserve the Chinese light workspace, supported methods, and output formats.
- Keep orchestration in the shared task service, independent of both UI layers.
- Never store API keys in browser storage, task snapshots, URLs or logs.
- Follow the surrounding naming and code style. Keep Skill instructions in
  Chinese and the README in English.
- Keep summary and practice rules separate. All AI adapters must use the shared
  rules; changes to prompts should not apply to just one provider.
- Update the README when behavior, setup, or dependencies change.
- Keep third-party attribution and license terms. New reference material needs
  a source, license, attribution, and a description of any changes.
- Exclude `output/`, `local_textbook/`, `local_problems/`, `local_practice/`, credentials, and build
  artifacts from commits and release archives.

Before submitting, run the backend tests and frontend build/browser tests:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend test
```

Check the changed behavior with a small example. Do not use
paid API calls just to check documentation or formatting changes. Mention what
you checked and any unavailable account or platform in the pull request.

GitHub Actions checks Python syntax, bundled JSON, and CLI `--help` on Windows
and Linux. It does not sign in, install system tools, fetch papers, call an AI,
or verify generated mathematics. A passing check does not replace testing the
behavior you changed.

## License and releases

Original code, rules, documentation, and templates contributed here use the
[MIT License](LICENSE). Third-party material retains its own license; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). No separate contributor
agreement is required.

Before publishing a release, check the archive contents as well as the commit:
`.gitignore` does not remove already tracked files or filter archives made by
zipping your working folder. Use the committed source as the release basis,
retain all license notices, and exclude local study and account data.

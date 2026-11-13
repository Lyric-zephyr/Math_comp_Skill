# Third-party notices

The [MIT License](LICENSE) covers original Course_Skill code, rules, documentation,
and templates. Third-party software and reference materials use the licenses
listed below.

## Bundled software

| Component | License | Included notice |
| --- | --- | --- |
| [KaTeX](https://katex.org/), including bundled math fonts | MIT | [LICENSE-KaTeX.txt](skills/Common/assets/web/LICENSE-KaTeX.txt) |
| [Marked](https://marked.js.org/) | MIT | [LICENSE-Marked.txt](skills/Common/assets/web/LICENSE-Marked.txt) |

Keep these notices when redistributing the corresponding JavaScript, CSS,
fonts, or exported standalone HTML containing those assets.

## Web workspace dependencies

The React frontend uses React/React DOM, Radix UI, Tailwind CSS, Lucide,
class-variance-authority, clsx and tailwind-merge, including their runtime
transitive dependencies. Button and Sheet components adapt the shadcn/ui patterns.
The bundled runtime license texts and attributions are collected in
[frontend/THIRD_PARTY_LICENSES.txt](frontend/THIRD_PARTY_LICENSES.txt); retain this
file when redistributing frontend builds. Build/test tools retain their own
package license terms. FastAPI, Uvicorn and psutil are separately installed
Python dependencies under their respective MIT/BSD licenses.

## Externally hosted reference selections

| Collection | Material in Assistant_course | Applicable license |
| --- | --- | --- |
| [MathNet](https://mathnet.mit.edu/) | Three selected calculus problems | CC BY 4.0, subject to the source record's rights information |
| [MIT OpenCourseWare](https://ocw.mit.edu/) | Six translated/adapted calculus problems | CC BY-NC-SA 4.0 |

These records are hosted in the separate Assistant_course repository.
See the [reference-material notice](https://github.com/Lyric-zephyr/Assistant_course/blob/main/Practice/Mathematics_Competition/Open_Problems/NOTICE.md)
and the individual JSON records for authors, original sources, license links,
and changes. MIT OCW material requires attribution, noncommercial use, and
share-alike licensing for adaptations.

## Separately installed tools

These are installed on the user's machine, rather than bundled in this source
repository:

- [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright):
  AGPL-3.0 or a commercial license from Artifex.
- [Playwright](https://github.com/microsoft/playwright-python/blob/main/LICENSE):
  Apache-2.0.
- Pandoc, MiKTeX/TeX Live packages, browsers, Node.js, and Codex CLI retain their
  respective terms. Browser fonts such as SimSun and SimHei are system fonts
  and are not bundled here.

## User material and competition papers

`local_textbook/`, `local_problems/`, and `output/` are local runtime data and
are excluded from version control. Publicly accessible competition PDFs are
not bundled or assigned an open license by this project. See the
[source-access notes](skills/Mathematics_Competition/references/source_access.md) for
runtime access behavior and restrictions.

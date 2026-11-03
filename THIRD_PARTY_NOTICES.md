# Third-party notices

The [MIT License](LICENSE) covers original MATH COMP code, rules, documentation,
and templates. It does not replace the licenses of dependencies or reference
materials. This repository is not affiliated with the AI providers, competition
organizers, or institutions listed below.

## Bundled software

| Component | License | Included notice |
| --- | --- | --- |
| [KaTeX](https://katex.org/), including bundled math fonts | MIT | [LICENSE-KaTeX.txt](skills/math-comp-prep/assets/web/LICENSE-KaTeX.txt) |
| [Marked](https://marked.js.org/) | MIT | [LICENSE-Marked.txt](skills/math-comp-prep/assets/web/LICENSE-Marked.txt) |

Keep these notices when redistributing the corresponding JavaScript, CSS,
fonts, or exported standalone HTML containing those assets.

## Bundled reference selections

| Collection | Included material | Applicable license |
| --- | --- | --- |
| [MathNet](https://mathnet.mit.edu/) | Three selected calculus problems | CC BY 4.0, subject to the source record's rights information |
| [MIT OpenCourseWare](https://ocw.mit.edu/) | Six translated/adapted calculus problems | CC BY-NC-SA 4.0 |

See the [reference-material notice](skills/math-comp-prep/assets/open_problems/NOTICE.md)
and the individual JSON records for authors, original sources, license links,
and changes. The MIT OCW selection has noncommercial and share-alike conditions;
it is not MIT-licensed project code. Do not assume every dataset record or
resource on a source website has the same license.

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

Review the applicable dependency terms before distributing an installer or
combined application, especially when including PyMuPDF. Installing a tool
does not change its license to the project's MIT license.

## User material and competition papers

`local_textbook/`, `local_problems/`, and `output/` are local runtime data and
are excluded from version control. Publicly accessible competition PDFs are
not bundled or assigned an open license by this project. See the
[source-access notes](skills/math-comp-prep/references/source_access.md) for
runtime access behavior and restrictions.

# 开放练习资料说明

本目录是少量附有来源的参考题目，不是完整题库，也不能代替非数学 A 类竞赛真题。
每条 JSON 记录均保留来源、署名、许可证及翻译或改动说明。

## MathNet 选题

三道微积分题选自 ICLR 2026 的 MathNet 数据集。作者为 Shaden Alshammari、Kevin
Wen、Abrar Zainal、Mark Hamilton、Navid Safaei、Sultan Albarakati、William T.
Freeman 和 Antonio Torralba：
<https://mathnet.mit.edu>.

核对日期为 2026-11-03。所选公开记录未另外标明题册版权人或冲突的题册许可证，
因此按数据集默认的 CC BY 4.0 许可处理：
<https://creativecommons.org/licenses/by/4.0/>.

中文题干保留原题数据；原始题干与解答保留原文，供核对来源。
MathNet 的许可说明优先尊重原权利人的明确声明，不能据此认为全部 MathNet
记录都可自由再分发。新增资料前应逐条检查权利信息：
<https://github.com/ShadeAlsha/MathNet#license>.

## MIT 开放课程选题

六道题翻译或改编自 MIT OpenCourseWare 的 **18.01SC 单变量微积分，2010 年秋季期末考试**：
<https://ocw.mit.edu/courses/18-01sc-single-variable-calculus-fall-2010/pages/final-exam/>.

所选资料及其译文采用 **CC BY-NC-SA 4.0（署名—非商业性使用—相同方式共享）**：
<https://creativecommons.org/licenses/by-nc-sa/4.0/>.
使用时需保留署名、标明改动、遵守非商业限制，改编内容按相同许可证共享。
还需核对 OCW 条款及个别资源的例外说明：<https://ocw.mit.edu/terms/>。

该许可与本项目代码的 MIT 许可分别适用。基于这些题目生成的改编内容，仍需保留
适用的署名与许可条款。本目录不附带原始 PDF。

## 竞赛真题 PDF

运行时索引覆盖第 1–17 届，并记录访问限制。默认在内存中读取允许访问的 PDF；
仅在明确运行 `--download-all` 时保存原文件，禁止访问的路径会跳过。
已有缓存不能绕过 robots、登录、密码或复制限制，也不代表获得再分发或向第三方
AI 发送内容的许可。`local_problems/`、索引和 OCR 缓存不应放入公开发行包。
具体观察及限制见 `references/source_access.md`。

## 文件内容怎么看

- `problem`：中文题干；`modules`：适用模块。
- `source`、`record_url`：原始来源链接；`attribution`：原始署名。
- `license`、`license_url`：许可证名称和条款链接。
- `changes`：中文翻译或改动说明。
- `original_problem`、MathNet 的 `solution`：保留的原始记录，不修改原作者文字。

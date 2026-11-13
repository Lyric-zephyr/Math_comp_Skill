---
name: course-common
description: 课程资料生成的共同排版、资料读取、知识总结与练习规则，由具体科目技能按任务加载。
---

# 课程共同规则

本目录集中维护脚本、模板和共同原则，同级英文科目目录只定义自身范围与题型。共同资料默认从 [Assistant_course](https://github.com/Lyric-zephyr/Assistant_course) 按需在线读取，用户无需下载资料包。

- 每次读取 [排版](references/formatting.md)、[资料读取](references/materials.md)。
- 总结读取 [知识总结](references/knowledge_summary.md)，不加载练习规则或题库。
- 练习读取 [练习规则](references/problem_set.md)，再加载对应科目的题型、难度与模块边界。
- 仅输出含 LaTeX 公式的 Markdown 正文，所选文件格式由启动器导出。

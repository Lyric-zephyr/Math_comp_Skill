# 真题来源与读取方式

核对日期：2026-11-03。

## 当前观察

- `http://www.cmathc.cn/` 的公开竞赛试题栏目包含 PDF 下载和微信公众号入口；此次 `/robots.txt` 返回 404。
- `https://www.cmathc.org.cn/robots.txt` 禁止自动访问 `/static/*`，程序跳过该路径下的 PDF，保留公开文章入口供用户查看。
- `https://www.cmathc.org.cn/st/560.html` 提供资料汇总入口，部分资源需要通过公众号或网盘查看。

## 程序行为

1. 索引覆盖第 1–17 届已发现的初赛、决赛入口，逐届报告可读取、需人工查看、受限和缺失状态。
2. 自动生成练习时优先在线读取 Assistant_course；官网补充读取的索引及 OCR 工作文件仅使用系统临时目录，结束后清理。手动点击来源索引或运行脚本时，报告默认保存在已被 Git 忽略的 `local_problems/`。
3. `--download-all` 尝试保存全部已发现且允许自动访问的 PDF；受限或失败的项目记录在报告中。
4. 遵守 robots、登录验证、PDF 密码和复制权限；无法核对访问规则时暂停读取，旧缓存不绕过当前限制。
5. 点击“真题来源（第1–17届）”查看报告和原始链接。生成练习时，选中的参考片段会发送给所选 AI。

## 资料使用

真题版权归原权利人，公开下载不等于开放授权；发布或向 AI 提供资料时，请遵守来源条款。项目不打包真题 PDF。开放选题的署名与许可见 [资料库说明](https://github.com/Lyric-zephyr/Assistant_course/blob/main/Practice/Mathematics_Competition/Open_Problems/NOTICE.md)。

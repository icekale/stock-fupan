# A 股收盘复盘 Wiki

欢迎来到 **A 股收盘复盘** 项目 Wiki。这个项目的核心目标是：每天基于真实行情、真实新闻与复盘源，生成一份可阅读、可留档、可迭代的本地 HTML 股票复盘报告。

> 当前定位：本地优先 MVP，不追求在线多用户 SaaS；优先把每日复盘报告做稳定、真实、好看、可复用。

## 项目核心原则

- **HTML 是第一产物**：最终报告以 `report.html` 为核心，PNG/JSON/数据库都是辅助资产。
- **不要 fake 内容**：生产级报告默认使用 TickFlow 行情、Anspire 新闻、同花顺/东方财富复盘源；真实数据失败时应显式失败。
- **TickFlow-only 行情**：已放弃 AkShare，行情路径统一使用 TickFlow。
- **本地部署优先**：结构化数据进入 SQLite，HTML/PNG/快照 JSON 进入本地文件目录。
- **自选股默认关闭**：自选股模块需要显式开启，避免影响主报告质量。

## Wiki 导航

- [[快速开始]]：本地安装、配置和一键生成报告。
- [[数据源与环境变量]]：TickFlow、Anspire、复盘源、LLM、OCR、自选股配置。
- [[每日报告生成流程]]：`make report DATE=YYYY-MM-DD` 的完整流程与输出说明。
- [[HTML 报告结构]]：报告模块、视觉风格、次日预测与仓位建议。
- [[开发与测试]]：后端、前端、测试、lint、Docker build。
- [[部署到 GitHub]]：当前 GitHub 发布状态与后续发布建议。
- [[故障排查]]：常见报错、数据源失败、端口打不开、Docker 问题。
- [[路线图]]：下一阶段可以继续做什么。

## 当前仓库

- GitHub 仓库：<https://github.com/icekale/stock-fupan>
- 当前主要分支：`main`
- 当前发布方式：GitHub 私有仓库；Docker Hub 暂不发布。

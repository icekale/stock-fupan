# A 股每日复盘助手

一个本地优先的 A 股每日复盘程序，用真实行情、新闻和复盘源生成可分享的 HTML/PNG 报告。项目目标不是生成泛泛而谈的市场摘要，而是围绕“当天最强势的板块和个股、前期强势主线的延续/退潮、次日可能继续强势的方向”做结构化复盘。

> 仅用于个人研究和复盘，不构成投资建议。

## 核心能力

- **真实数据优先**：TickFlow 和 Anspire 是主要数据源，不在生产报告中使用 fake 内容。
- **强势主线识别**：从全市场行情中提取当日强势板块、前排个股、涨跌幅、成交额和强度排名。
- **新闻催化分析**：使用 Anspire 搜索新闻，辅助判断板块强势是否有事件催化。
- **复盘源校验**：同花顺复盘和东方财富涨停复盘作为辅助源，用于校验题材、封板质量和市场情绪。
- **前期主线跟踪**：对昨日或历史强势方向做延续、分化、退潮判断，例如半导体、先进封装、存储芯片等。
- **次日观察模块**：把强度、前排股、封板质量、持续性和催化转成次日观察条件。
- **HTML/PNG 输出**：生成结构化 `report.html`，并导出适合分享的 `report.png`。
- **自选股导入**：支持同花顺 `.blk`、CSV、纯文本代码和 OCR 图片导入；报告里的自选股模块默认关闭。

## 数据源优先级

| 层级 | 数据源 | 用途 |
| --- | --- | --- |
| 主源 | TickFlow | 指数、全市场行情、板块强度、前排个股、成交额、核心股当日校验 |
| 主源 | Anspire | 新闻搜索、题材催化、事件解释 |
| 辅助源 | 同花顺复盘 | 题材语义、热门方向、市场复盘文本 |
| 辅助源 | 东方财富涨停复盘 | 涨停复盘、封板率、市场质量 |
| 跟踪源 | 历史 HTML / 快照 JSON | 前期强势主线延续性跟踪 |

## 推荐部署：Docker Compose

### 1. 克隆项目

```bash
git clone https://github.com/icekale/stock-fupan.git
cd stock-fupan
```

### 2. 创建本地环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少填写：

```dotenv
TICKFLOW_API_KEY=你的_TickFlow_Key
ANSPIRE_API_KEY=你的_Anspire_Key

MARKET_PROVIDER=tickflow
NEWS_PROVIDER=anspire
TICKFLOW_PROVIDER=tickflow
REVIEW_SOURCES_ENABLED=true
REPORT_WATCHLIST_ENABLED=false
```

如果你希望本地生产级报告在数据源失败时直接失败，而不是回退到 fake 数据，建议设置：

```dotenv
APP_ENV=production
PROVIDER_FALLBACK_ENABLED=false
OCR_FALLBACK_ENABLED=false
PRODUCTION_ALLOW_FAKE_PROVIDERS=false
```

### 3. 启动服务

```bash
docker compose up --build
```

启动后访问：

- Web 前端：`http://localhost:3000`
- API 服务：`http://localhost:8000`

### 4. 生成每日复盘报告

可以在本机仓库根目录运行：

```bash
make report DATE=2026-05-27
```

生成后会在终端打印：

- `report.html`
- `snapshot.json`
- provider 状态，例如 TickFlow、Anspire、同花顺、东方财富是否成功

报告文件默认写入：

```text
reports/YYYY-MM-DD/close/vXXX/
```

其中常用产物：

```text
report.html   # 核心 HTML 复盘报告
report.png    # 可分享长图
snapshot.json # 本次报告的结构化快照
```

### 5. 本地预览报告

进入终端打印出来的版本目录：

```bash
cd reports/2026-05-27/close/vXXX
python3 -m http.server 8888 --bind 127.0.0.1
```

然后打开：

```text
http://127.0.0.1:8888/report.html
```

## 本地开发

### 后端 API

```bash
cd apps/api
uv sync
uv run playwright install chromium
uv run uvicorn app.main:app --reload --port 8000
```

### 前端 Web

```bash
corepack enable
pnpm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 pnpm dev:web
```

打开：

```text
http://localhost:3000
```

## 常用配置

```dotenv
DATABASE_URL=sqlite:///./data/stock_review.db
REPORTS_ROOT=../../reports

TICKFLOW_API_KEY=
TICKFLOW_BASE_URL=https://api.tickflow.org
TICKFLOW_PROVIDER=tickflow

ANSPIRE_API_KEY=
ANSPIRE_BASE_URL=https://plugin.anspire.cn/api/ntsearch/search

MARKET_PROVIDER=tickflow
NEWS_PROVIDER=anspire
REVIEW_SOURCES_ENABLED=true
THS_FUPAN_URL=https://stock.10jqka.com.cn/fupan/
EASTMONEY_ZTFP_URL=https://stock.eastmoney.com/a/cztfp.html

REPORT_WATCHLIST_ENABLED=false
WATCHLIST_PROVIDER=local
WATCHLIST_SNAPSHOT_ROOT=./data/watchlists

OCR_PROVIDER=fake
OCR_FALLBACK_ENABLED=true
```

## 自选股与 OCR

自选股模块默认关闭：

```dotenv
REPORT_WATCHLIST_ENABLED=false
```

需要在报告中加入自选股观察时改为：

```dotenv
REPORT_WATCHLIST_ENABLED=true
```

支持导入：

- 同花顺 `.blk`
- CSV
- 纯文本股票代码
- 图片 OCR 识别

OCR 默认使用 fake provider 方便本地开发。如果要启用真实 OCR，可配置 OpenAI 兼容视觉模型。

## 项目结构

```text
apps/api/          # FastAPI 后端、报告生成、数据源 provider、HTML/PNG 渲染
apps/web/          # Next.js 前端
reports/           # 本地生成的报告产物，默认不提交到 Git
docker-compose.yml # 推荐部署入口
.env.example       # 环境变量示例
```

## 验证

后端测试：

```bash
cd apps/api
.venv/bin/python -m ruff check app tests
.venv/bin/python -m pytest -q
```

前端类型检查：

```bash
corepack pnpm --filter @stock-review/web test
```

## 注意事项

- `.env`、`apps/api/.env`、`reports/`、`apps/api/data/` 默认不提交。
- API Key 只应放在本地环境变量或 `.env` 中。
- 生产级报告建议关闭 fake fallback，让数据源失败显式暴露。
- 生成内容是复盘研究工具，不是买卖建议。

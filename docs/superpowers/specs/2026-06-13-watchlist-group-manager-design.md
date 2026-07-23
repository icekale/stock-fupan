# 自选股分组管理设计

## 背景

当前自选股是导入快照：文本、CSV、OCR 导入后生成一批 `watchlist_items`，日报读取最新导入结果。这个模型适合“临时导入”，不适合长期维护自选股、分组、标签和每日风险检测。

本次目标是把自选股升级成可编辑股票池，操作逻辑参考同花顺 App：左侧分组筛选，股票可同时属于多个分组，单股或批量编辑所属分组。

## 范围

包含：

- 新增自选股管理页面入口。
- 支持新增、改名、删除自定义分组。
- 支持手动添加股票，导入文本/CSV/OCR 后进入自选池。
- 支持单只股票编辑所属分组。
- 支持多选股票批量加入或移出分组。
- 支持一个股票同时属于多个分组。
- 删除分组时只删除分组关系，不删除股票。
- 日报和每日风险检测默认读取“自选”股票池，后续可扩展为读取指定分组。

不包含：

- 不做盘中监控。
- 不做拖拽排序。
- 不做云同步。
- 不删除股票历史导入快照，只让新股票池成为主要读取来源。

## 数据模型

保留现有 `watchlist_imports` / `watchlist_items` 作为导入记录和审计快照。

新增长期管理表：

- `watchlist_stocks`
  - `id`
  - `symbol`
  - `code`
  - `exchange`
  - `name`
  - `note`
  - `created_at`
  - `updated_at`

- `watchlist_groups`
  - `id`
  - `name`
  - `is_default`
  - `sort_order`
  - `created_at`
  - `updated_at`

- `watchlist_stock_groups`
  - `stock_id`
  - `group_id`
  - `created_at`

- `watchlist_tags`
  - `id`
  - `name`
  - `sort_order`

- `watchlist_stock_tags`
  - `stock_id`
  - `tag_id`

默认分组：

- `全部` 是虚拟分组，不入库或只读展示，不可删除。
- `自选` 是默认分组，系统初始化时创建，不建议删除；实现上先设为不可删除，避免日报/风险检测失去默认股票池。

## API

新增 API：

- `GET /api/watchlists/pool`
  - 返回分组、标签、股票列表、每只股票所属分组和标签。

- `POST /api/watchlists/stocks`
  - 添加单只股票。
  - 默认加入 `自选` 分组。

- `PATCH /api/watchlists/stocks/{stock_id}`
  - 编辑名称、备注、标签、所属分组。

- `DELETE /api/watchlists/stocks/{stock_id}`
  - 从自选股池删除股票。

- `POST /api/watchlists/groups`
  - 新建分组。

- `PATCH /api/watchlists/groups/{group_id}`
  - 重命名分组。

- `DELETE /api/watchlists/groups/{group_id}`
  - 删除自定义分组。
  - 只删除 `watchlist_stock_groups` 关系和分组本身，不删除股票。
  - `全部` 和 `自选` 不允许删除。

- `POST /api/watchlists/stocks/bulk-groups`
  - 批量设置或追加分组。

现有导入 API 行为调整：

- `POST /api/watchlists/import-text`
- `POST /api/watchlists/import-file`
- `POST /api/watchlists/ocr-confirm`

导入成功后，除了保存导入快照，也要 upsert 到 `watchlist_stocks`，并默认加入 `自选` 分组。

## 页面交互

新增独立的自选股管理页，左侧导航入口从“自选股导入”改为“自选股”。

页面布局：

- 左侧窄栏：分组列表和标签筛选。
- 中间主区：搜索、批量操作、股票表格。
- 右侧抽屉或侧栏：编辑股票所属分组和标签。

核心操作：

- 点击左侧分组，主表过滤该分组股票。
- 点击“新建分组”，输入名称后创建。
- 点击分组菜单可改名或删除。
- 删除分组弹确认：`删除分组「MLCC」？组内股票会保留在自选股中。`
- 勾选多只股票后，顶部显示批量操作条，可加入分组、移出当前分组、删除股票。
- 单只股票点“编辑分组”，右侧面板勾选多个分组后保存。
- 股票行展示所属分组 pill，便于确认一个股票是否在多个分组内。

## 日报与风险检测

短期：

- 日报和每日风险检测读取 `自选` 默认分组。
- 如果新表为空但旧导入快照存在，允许回退读取最新导入快照，避免旧用户数据瞬间消失。

后续：

- 报告生成面板可增加“自选股范围”下拉：自选、MLCC、电力、存储芯片等。
- 风险检测也可按分组运行。

## 错误处理

- 重名分组：返回 422，并提示“分组名已存在”。
- 删除默认分组：返回 400。
- 删除不存在分组或股票：返回 404。
- 股票重复添加：更新已有股票信息，并保留原有分组关系。
- 批量分组操作中部分股票不存在：返回 422，前端提示失败，不做部分成功。

## 测试

后端：

- 导入文本会 upsert 股票池并加入自选分组。
- 一个股票可属于多个分组。
- 删除分组不删除股票。
- 默认分组不可删除。
- 日报读取新股票池，空池时回退旧快照。

前端：

- 页面包含分组列表、标签筛选、股票表格、批量加入分组入口。
- 删除分组文案说明“不删除股票”。
- API client 覆盖 group/stocks/bulk-groups。

浏览器：

- 打开自选股页，新增分组，添加股票，批量加入分组。
- 删除自定义分组后，股票仍在“自选/全部”中。

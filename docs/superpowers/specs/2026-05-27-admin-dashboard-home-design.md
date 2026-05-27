# 后台首页 MVP 设计

## 目标

把当前单页报告生成器升级为真正的本地后台首页：左侧菜单、报告生成、历史报告列表、HTML/PNG 查看入口和数据源配置状态。重点是让用户打开 Web 后能一眼知道“现在能生成什么、最近生成了什么、数据源是否正常”。

## 范围

本阶段只做本地 MVP，不做账号、权限、在线配置保存、删除报告、复杂筛选和多页面路由。所有配置状态只读展示，不显示 API Key 明文。

## 页面结构

- 左侧菜单：`概览`、`报告生成`、`历史报告`、`数据源状态`、`自选股导入`。
- 顶部摘要：显示当前后台名称、主要数据源优先级、API 健康提示。
- 报告生成区：保留交易日输入、全日盘后复盘/午间复盘切换和生成按钮。
- 历史报告区：展示最近报告，包含交易日、类型、版本、状态、创建时间、HTML/PNG 打开链接。
- 数据源状态区：展示 TickFlow、Anspire、同花顺、东方财富、自选股模块、OCR 的配置/启用状态。
- 自选股导入区：保留现有导入组件，默认仍可折叠在侧栏下方或主区域底部。

## 后端接口

新增 `GET /api/config/status`，返回只读状态：

```json
{
  "items": [
    {"name": "TickFlow", "role": "主源 · 行情", "configured": true, "enabled": true, "status": "ready", "detail": "MARKET_PROVIDER=tickflow"},
    {"name": "Anspire", "role": "主源 · 新闻", "configured": true, "enabled": true, "status": "ready", "detail": "NEWS_PROVIDER=anspire"}
  ]
}
```

状态规则：

- `ready`：启用且必要 key 已配置。
- `missing_key`：启用但必要 key 未配置。
- `disabled`：功能未启用或 provider 不是该源。
- `local`：本地功能，无外部 key 要求。

## 前端实现

继续使用 `apps/web/app/page.tsx` 作为首页，拆出小组件控制复杂度：

- `components/AdminShell.tsx`：负责左侧菜单和整体两栏布局。
- `components/DataSourceStatusPanel.tsx`：展示配置状态。
- 复用现有 `ReportPreview`、`WatchlistImportPanel`、`ProviderStatusPanel`。
- 在 `lib/api.ts` 增加 `getConfigStatus()`。
- 在 `lib/types.ts` 增加 `ConfigStatusItem` 和 `ConfigStatusResponse`。

视觉方向：`quiet operations console`。使用克制的浅色企业后台风格，左侧菜单固定，主内容分区明确，状态用小色点和标签而不是大面积颜色。

## 测试与验收

- 后端测试：`GET /api/config/status` 不泄露 key，能正确标识主源和辅助源状态。
- 前端类型检查：`corepack pnpm --filter @stock-review/web test`。
- 浏览器验收：打开后台首页能看到左侧菜单、报告生成、历史报告、数据源状态；HTML/PNG 链接仍可打开。

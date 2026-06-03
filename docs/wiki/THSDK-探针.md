# THSDK 探针

`thsdk` 是实验性同花顺辅助源，默认关闭。开启 `THSDK_ENABLED=true` 后，会作为辅助复盘源参与报告证据，不替代 TickFlow / Anspire。

## 目标

- 验证本机或 Unraid 容器能否加载 `thsdk` 及其同花顺动态库。
- 验证游客或正式同花顺账号是否能拿到真实数据。
- 判断它是否适合补充 D 日报里的同花顺概念/主题、问财涨停连板、竞价异动和大单数据。

## 本地快速检查

不安装 `thsdk` 时，脚本应该返回结构化 JSON，而不是抛 traceback：

```bash
cd apps/api
uv run python scripts/probe_thsdk.py --skip-live
```

项目已固定安装 `thsdk` 依赖，可直接执行真实探测：

```bash
cd apps/api
uv run python scripts/probe_thsdk.py
```

如果有正式同花顺账号，建议用环境变量注入：

```bash
export THS_USERNAME=你的账号
export THS_PASSWORD=你的密码
export THS_MAC=你的机器 MAC
uv run python scripts/probe_thsdk.py
```

## 探测内容

- `complete_ths_code`：补全 A 股同花顺代码。
- `wencai_nlp`：问财自然语言筛选，默认查询“今日涨停”。
- `ths_concept`：同花顺概念/主题列表。
- `market_data_block`：同花顺板块行情样例。
- `klines`：个股 K 线样例。
- `intraday_data`：个股分时样例。

## 接入标准

满足以下条件后，再考虑接入正式报告：

- 至少两类探测项稳定返回真实数据。
- `wencai_nlp`、`ths_concept` 或 `market_data_block` 至少一项可用。
- 失败时能清楚返回原因，不影响 TickFlow / Anspire 主流程。
- Unraid 容器内也能跑通。

## 报告接入方式

- 默认 `THSDK_ENABLED=false`，不参与正式报告。
- 开启后，THSDK 会通过问财获取“今日涨停、连续涨停天数、所属概念”和“今日连板股、所属概念”。
- 报告会把涨停/连板股的所属概念提炼成辅助主题证据，把前排股写入对应强势板块。
- ST 个股和常见噪音概念会被过滤，避免污染强势主线判断。

## 当前定位

数据源优先级保持不变：

1. TickFlow：主行情源。
2. Anspire：主新闻源。
3. 同花顺复盘 / 东方财富涨停复盘：辅助复盘源。
4. THSDK：实验性同花顺问财/概念辅助源，默认关闭。

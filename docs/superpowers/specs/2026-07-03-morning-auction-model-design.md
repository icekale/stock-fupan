# 早盘竞价收益模型 V1 设计

日期：2026-07-03
状态：已确认设计，待用户审阅

## 目标

构建一个早盘集合竞价选股模型，用于在 9:25 集合竞价结束后、9:30 开盘前输出强势候选池。

V1 不直接预测涨停，也不输出自动买入指令。模型目标是预测：

```text
9:30 开盘买入，持有到当日收盘，收益达到或超过 3% 的概率。
```

`>=5%` 不作为主训练标签，而作为强势票升级、精选池质量评估和回测分层指标。

本模块定位为研究和早盘筛选器，不接账户、不自动交易、不承诺固定胜率。

## 已确认决策

- 采用两阶段模型：规则过滤器 + 机器学习分类模型。
- V1 主标签使用 `open_to_close_return >= 3%`。
- `open_to_close_return >= 5%` 作为强势标签和回测验证指标。
- 样本特征只能使用 9:25 前可获得的数据。
- 标签可以使用当日收盘价。
- 第一版优先跑通数据集、特征生成、训练、回测和 9:28 输出，不急于做双模型融合。
- 第一版先做命令行训练、回测和预测，Web 后台后续再接。

## 非目标

- 不自动下单。
- 不接真实账户、仓位或券商交易接口。
- 不把预测结果描述成买入指令。
- 不做盘中实时交易助手。
- 不把当日最高价、当日收盘涨幅、盘中资金流等未来信息放进训练特征。
- 不强行凑 56 个因子；V1 先做 30 到 40 个稳定、可回放的因子。
- 不让资金、龙虎榜等增强数据源阻塞 V1 主流程。

## 标签设计

核心收益字段：

```text
open_to_close_return = close_price / open_price - 1
```

训练与评估标签：

```text
main_label = open_to_close_return >= 3%
strong_label = open_to_close_return >= 5%
safe_label = open_to_close_return > 0
risk_label = open_to_close_return <= -3%
```

V1 主模型训练 `main_label`，即预测 `>=3%` 的概率。

`strong_label` 用于：

- 精选池升级判断。
- 回测分层。
- 判断模型 Top N 是否真的能抓到强势弹性票。

## 样本池

V1 不做全市场无差别训练。每日先生成“早盘可交易候选池”，再由模型排序。

候选池过滤：

```text
A 股主板优先
剔除 ST / *ST
剔除上市不足 100 天
剔除停牌、无开盘价、成交异常
剔除一字涨停或明显无法买入
剔除竞价涨幅过高，例如 >= 8%
保留竞价活跃、近期强势、板块强势、近 20 日有涨停痕迹的股票
```

候选池不宜过窄。若每日只剩几十只候选，模型容易过拟合；V1 目标是每天保留大约 200 到 800 只可排序样本。

## 数据源边界

V1 免费数据底座优先使用 `simonlin1212/a-stock-data` 对应的本地 provider 能力。它适合覆盖日 K、实时行情、板块、资金、龙虎榜、涨停/热点等训练基础字段，但不能假设它能回放过去几百天的完整 9:15-9:25 集合竞价快照。

数据源分层：

```text
免费基础源：a-stock-data，本地映射到 mootdx、腾讯财经、百度股市通、东财、同花顺等公开接口
冷启动训练：先使用 a-stock-data 可覆盖的日 K、技术指标、涨停基因、板块、资金、龙虎榜字段
竞价实时采集：从启用日起每日 9:15-9:25 自采集快照并落库
历史竞价缺口：若没有付费源或既有落库数据，不能回填完整历史竞价序列
付费增强源：QMT/iFinD/TickFlow 等仅作为后续补齐历史竞价或更稳定盘口回放的增强项
```

字段覆盖：

```text
竞价数据：9:15-9:25 快照，至少需要 9:25 开盘价、竞价量、竞价额、委买委卖、未匹配量；历史数据优先来自自采集落库
日 K 数据：a-stock-data 的 mootdx / 百度股市通，前复权开高低收、成交量、成交额、换手率，至少 120-250 个交易日
实时行情与基础信息：a-stock-data 的腾讯财经，市值、换手率、涨跌停价、指数/ETF 等
资金数据：a-stock-data 的东财资金流，近 3 日/5 日主力净流入、大单净量；拿不到不阻塞 V1
板块数据：a-stock-data 的东财行业/概念和同花顺热点，所属行业/概念、板块涨幅、板块涨停数、板块强度排名
特殊数据：a-stock-data 的龙虎榜、昨日涨停/炸板/连板信息，作为增强因子
```

冷启动策略：

- 第一阶段先训练“无历史竞价序列”的弱版本，特征来自日 K、技术指标、板块、资金、龙虎榜和近期涨停基因。
- 第二阶段每天 9:15-9:25 采集竞价快照，积累真实竞价训练样本。
- 当竞价样本积累到足够交易日后，再把 `auction_last_minute_strength`、委买委卖变化和未匹配量方向加入主模型。
- 若需要立即训练完整竞价模型，必须接入能提供历史集合竞价回放的数据源；不能用当日收盘或盘中结果反推竞价特征。

数据时间边界：

- 训练特征只能使用 9:25 前可获得的数据。
- 训练标签可以使用当日收盘价。
- 预测时必须复用训练时的特征生成器、缺失值处理、分位数裁剪和特征列顺序。

## 因子设计

V1 使用 5 类因子，先做 30 到 40 个稳定字段。

### 今日竞价因子

```text
auction_return：竞价涨幅
auction_volume_ratio：竞价量 / 近 5 日成交量均值
auction_amount_ratio：竞价额 / 近 5 日成交额均值
auction_turnover_est：竞价估算换手
bid_ask_imbalance：委买委卖差
unmatched_buy_ratio：未匹配买量占比
auction_last_minute_strength：9:24-9:25 强度变化
auction_open_gap_vs_prev_close：开盘跳空幅度
```

### 昨日及近期行情因子

```text
prev_return：昨日涨跌幅
prev_turnover：昨日换手率
return_3d / return_5d / return_10d / return_20d
volume_ratio_3d / volume_ratio_5d
amount_ratio_3d / amount_ratio_5d
limit_up_count_20d：近 20 日涨停次数
days_since_last_limit_up：距上次涨停天数
market_cap_float：流通市值
```

### 技术指标因子

```text
close_vs_ma5 / close_vs_ma10 / close_vs_ma20
ma5_vs_ma20
ma_slope_5 / ma_slope_10
rsi6
rsi6_vs_rsi12
macd_hist
new_high_60d
new_high_120d
red_body_avg_vs_green_body_avg
upper_shadow_ratio_prev
```

### 历史股性与资金痕迹

```text
limit_up_count_15d
failed_limit_up_count_10d
board_break_repair_signal
main_net_inflow_3d
large_order_net_ratio_3d
dragon_tiger_recent_flag
institution_net_buy_recent
hot_money_seat_recent
```

资金和龙虎榜字段可为空。缺失时应保留缺失标记，不能让训练或预测失败。

### 衍生与交叉因子

```text
auction_return_x_volume_ratio
auction_strength_x_limit_up_gene
auction_strength_x_sector_strength
trend_score_x_auction_strength
capital_score_x_auction_strength
risk_score
```

## 模型结构

V1 使用两阶段结构。

阶段 1：规则过滤器

```text
剔除不可交易样本
剔除竞价过热样本
剔除流动性差样本
剔除趋势明显破位样本
剔除关键数据不完整样本
```

阶段 2：分类模型

```text
训练目标：P(open_to_close_return >= 3%)
模型选择：CatBoost 或 LightGBM 单模型优先
类别不平衡：使用 class_weight 或 scale_pos_weight
输出：prob_3pct、strong_5pct_score、bucket、reasons、risk_flags
```

V1 不做 CatBoost + XGBoost 融合。等数据质量、回测和真实早盘跟踪稳定后，再评估双模型融合。

## 训练流程

训练命令生成训练数据、模型和元数据。

要求：

- 按交易日做时间序列切分，不能随机打散。
- 使用训练集统计量处理缺失值、中位数填充和分位数裁剪。
- 持久化特征列顺序、缺失值策略、分位数边界和模型版本。
- 每次训练产出 `model_version`、`feature_version`、`train_date_range`。

建议产物：

```text
model.pkl 或 model.cbm
feature_config.json
preprocessor_stats.json
train_metrics.json
```

## 回测流程

回测必须模拟真实可用信息。

口径：

```text
买入价：当日开盘价
卖出价：当日收盘价
候选时间：只使用 9:25 前特征
交易限制：剔除一字板、停牌、无成交、开盘无法合理买入
成本：V1 记录无成本收益，同时预留手续费/滑点字段
```

核心指标：

```text
Top 1 / Top 3 / Top 5 平均收益
Top 3 / Top 5 命中 >=3% 比例
Top 3 / Top 5 命中 >=5% 比例
Top 3 / Top 5 亏损率
单日最大亏损
连续回撤天数
分行情状态表现：强势市、震荡市、退潮市
```

不能只看准确率。对于早盘筛选器，Top N 收益、亏损率和回撤比整体分类准确率更重要。

## 早盘运行流程

```text
08:55  启动任务，检查数据源、模型版本、交易日
09:15  开始采集竞价快照
09:20  标记可撤单阶段数据，仅作参考
09:25  固化最终竞价特征
09:26  生成候选池并跑规则过滤
09:27  模型推理与排序
09:28  输出精选池、强攻池、观察池、回避原因
09:30  不自动交易，只作为人工决策候选
15:10  回填收盘价，生成当日命中复盘
```

输出分层：

```text
精选池：高概率达到 >=3%，且强势因子支持冲击 >=5%
强攻池：>=5% 信号突出，但数量少、波动大
观察池：有强势迹象，但概率或风险过滤不够
回避池：竞价热但趋势、板块、量价或流动性风险明显
```

## 项目结构

模块放在现有 `apps/api` 下，作为独立服务，不混入日报主流程。

```text
apps/api/app/services/morning_auction/
  dataset.py        # 构建训练样本与标签
  features.py       # 统一特征计算，训练/预测共用
  filters.py        # 两阶段里的规则过滤器
  trainer.py        # 训练 CatBoost/LightGBM
  backtest.py       # 时间序列回测
  predictor.py      # 9:25 后推理排序
  schemas.py        # 样本、特征、预测结果 DTO
  artifacts.py      # 模型、特征统计量、版本元数据读写
```

命令行入口：

```text
python -m app.cli.morning_auction build-dataset --start 2024-01-01 --end 2026-06-30
python -m app.cli.morning_auction train --dataset data/morning_auction/dataset.parquet
python -m app.cli.morning_auction backtest --model artifacts/morning_auction/latest
python -m app.cli.morning_auction predict --trade-date 2026-07-03
```

文件产物：

```text
data/morning_auction/datasets/
data/morning_auction/predictions/
artifacts/morning_auction/models/
artifacts/morning_auction/preprocessors/
artifacts/morning_auction/backtests/
```

## API 设计

V1 先提供预测和运行查询接口。

```text
POST /api/morning-auction/predict
GET  /api/morning-auction/runs/{run_id}
```

预测返回：

```text
trade_date
model_version
feature_version
source_status
selected_pool
attack_pool
watch_pool
avoid_pool
items[]
```

候选项字段：

```text
symbol
name
prob_3pct
strong_5pct_score
bucket
auction_reasons
trend_reasons
sector_reasons
risk_flags
data_quality
```

## 测试与验收

单元测试：

- 标签计算：`main_label`、`strong_label`、`safe_label`、`risk_label`。
- 规则过滤：ST、停牌、一字板、竞价过热、数据缺失。
- 特征生成：训练和预测对同一输入生成同一列顺序。
- 预处理统计量：训练保存、预测加载，不重新估计。
- 时间切分：验证集日期必须晚于训练集日期。

回测验收：

- 不使用 9:25 后数据生成特征。
- 回测可复现同一模型版本的 Top N 结果。
- 输出 Top 1/3/5 收益、`>=3%` 命中率、`>=5%` 命中率、亏损率和回撤。
- 数据源缺失时给出明确降级原因，而不是输出伪造结果。

早盘预测验收：

- 9:25 特征固化后可在 9:28 前输出结果。
- 结果包含候选池、分层、原因、风险标记和模型版本。
- 不包含自动交易、仓位指令或保证性收益表述。

## 风险与后续迭代

主要风险：

- 竞价数据源延迟或字段口径变化。
- `>=3%` 样本仍然存在不平衡，需要通过类别权重和 Top N 评估处理。
- 候选池过窄会导致过拟合，过宽会降低信号密度。
- 极端市场环境下模型可能失效。

后续迭代：

- 接入 2 到 4 周真实早盘跟踪结果后，评估阈值和候选池边界。
- 增加动态阈值：强势市放宽、退潮市收紧。
- 增加板块共振：同板块多只股票同时出信号时加分。
- 评估 CatBoost + XGBoost 融合。
- 在 Web 后台加入早盘候选展示和盘后复盘结果。

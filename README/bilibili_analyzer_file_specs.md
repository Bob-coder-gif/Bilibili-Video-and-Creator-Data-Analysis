# bilibili-analyzer 文件职责说明

每个文件具体做什么、包含哪些函数/类、输入输出是什么。

---

## app/main.py

**职责：** 轻量入口，仅做参数解析和流程分发，不包含业务逻辑。

```
main()
  ├── 解析命令行参数（--mid, --horizon, --mode）
  ├── 读取 config/settings.py 配置
  └── 调用 pipeline/run_pipeline.py 的 run() 启动流程
```

---

## crawler/bilibili_client.py

**职责：** 封装所有与 B 站 API 的底层通信，上层模块不直接调用 HTTP。

```
class BilibiliClient
  ├── __init__(credential=None)     # 可选传入登录凭证（Credential 对象）
  ├── get_user_info(mid)            # 拉取 UP 主基本信息（名称、粉丝数）
  ├── get_video_list(mid, pn, ps)   # 分页拉取视频列表（单页）
  ├── get_video_stat(bvid)          # 拉取单条视频的详细 stat（点赞/投币/收藏）
  └── _handle_rate_limit()          # 请求限流：失败自动 sleep 重试
```

- 依赖：`bilibili-api-python`
- 输出：原始 dict（API 响应体），不做业务转换

---

## crawler/fetch_videos.py

**职责：** 调用 BilibiliClient，将原始 API 响应转换为项目内部数据结构。

```
fetch_uploader_profile(mid, client, max_videos=500)
  ├── 循环调用 client.get_video_list() 分页拉取
  ├── 对每条视频调用 client.get_video_stat() 补全点赞/投币/收藏
  ├── 将 dict 转换为 Video / VideoStats 对象
  └── 返回 UploaderProfile

fetch_follower_history(mid, client)
  ├── 拉取粉丝数历史快照（若 API 支持）
  └── 返回 [(datetime, follower_count), ...]
```

- 输入：mid（UP 主 UID）、BilibiliClient 实例
- 输出：`UploaderProfile` 对象

---

## models/video.py

**职责：** 定义项目全局数据结构，所有模块共享此契约，不含任何业务逻辑。

```
@dataclass VideoStats
  ├── view, like, coin, favorite, share, reply, danmaku   # 各项统计字段
  └── engagement (property)                               # 三连合计 = like+coin+favorite

@dataclass Video
  ├── bvid, title, pubdate, duration, stats, tags         # 基本字段
  └── pubdate_week (property)                             # 返回 "2024-W03"，周粒度聚合用

@dataclass UploaderProfile
  ├── mid, name, videos, follower_history                 # UP 主信息
  └── videos_sorted() (method)                           # 按发布时间升序返回视频列表
```

---

## models/ml/trainer.py

**职责：** 训练四个预测目标各自独立的 XGBoost 模型，保存到磁盘。

```
train_all_targets(df, params=None, n_splits=5, save=True)
  ├── 遍历 TARGET_COLS = [view, follower_gain, engagement, video_count]
  ├── 对每个目标调用 _train_single()
  ├── 打印各目标的交叉验证 MAE
  └── 调用 _save_models() 持久化

_train_single(X, y, params, n_splits)
  ├── 使用 TimeSeriesSplit 做时序交叉验证（禁止随机 split）
  ├── 记录每折 MAE
  └── 全量数据重新训练一次，返回最终模型

_save_models(models, feature_cols)
  ├── 每个模型保存为 data/processed/models/{target}.ubj
  └── 特征列顺序保存为 feature_cols.json（推理时对齐用）
```

- 输入：`build_feature_matrix()` 的输出 DataFrame
- 输出：`{ target_name: XGBRegressor }` + 磁盘文件

---

## models/ml/predictor.py

**职责：** 加载已训练模型，执行自回归滚动多步预测。

```
class BilibiliPredictor
  ├── __init__(models, feature_cols)
  ├── load(model_dir) [classmethod]     # 从磁盘加载模型 + feature_cols.json
  ├── predict(history_df, horizon=4)    # 主预测入口，返回未来 N 周 DataFrame
  └── _build_next_row(df, next_week)    # 根据当前历史构造下一行特征（滞后+滚动）

predict() 滚动逻辑：
  for step in range(horizon):
    ├── 构造下一周特征行
    ├── 四个模型各自预测
    ├── 预测值写回历史 df（供下一步使用）
    └── 收集结果
```

- 输入：历史特征 DataFrame（来自 `build_feature_matrix()`）
- 输出：未来 N 周 DataFrame，列为四个预测目标，索引为 Period[W]

---

## models/ml/evaluator.py

**职责：** 量化模型效果，提供回测误差、特征重要性、置信区间三类评估。

```
backtest(df, models, test_weeks=8)
  ├── 末尾 test_weeks 周作为测试集，前面全部作为训练集
  ├── 计算每个目标的 MAE / MAPE / RMSE
  └── 返回误差汇总 DataFrame

feature_importance(models, feature_cols, top_n=15)
  ├── 提取每个模型的 XGBoost gain 重要性
  └── 返回 { target: pd.Series(feature -> importance) }

predict_with_interval(model_median, X, alpha=0.1)
  ├── 用分位数回归模型估计置信区间（P10 ~ P90）
  └── 返回 DataFrame，列：pred / lower / upper

print_evaluation_report(df, models)
  └── 汇总打印回测误差 + Top5 重要特征
```

---

## features/feature_builder.py

**职责：** 将 `UploaderProfile` 原始数据转换为机器学习可用的特征矩阵，是数据层与模型层之间的核心桥梁。

```
build_feature_matrix(profile, dropna=True)     ← 主入口
  ├── build_weekly_base(profile)
  │     ├── 按自然周（Period[W]）聚合视频指标
  │     └── reindex 补全缺失周，填 0，保证时间轴连续
  ├── attach_follower_gain(weekly, profile)
  │     ├── 粉丝快照按周取最后一个值
  │     └── diff() 得到周增量
  ├── add_lag_features(df, cols)
  │     └── 滞后 1/2/3/4/8 周，命名规则：{col}_lag{n}
  ├── add_rolling_features(df, cols)
  │     └── 滚动 3/8 周均值 & 标准差，命名：{col}_roll{n}_mean/std
  └── add_time_features(df)
        ├── week_of_year / month / quarter
        ├── is_year_end / is_new_year（节假日周标记）
        └── week_sin / week_cos（正余弦编码，防止首尾不连续）

get_feature_cols(df)
  └── 返回特征列名列表（排除四个目标列本身）
```

- 输入：`UploaderProfile`
- 输出：以 Period[W] 为索引的 `pd.DataFrame`，含目标列 + 所有特征列

---

## analysis/metrics.py

**职责：** 计算单个 UP 主的基础统计指标，供 scoring 和可视化使用。

```
calc_avg_view(profile)              # 平均单视频播放量
calc_growth_rate(weekly_df, col)    # 指定列的周环比增长率序列
calc_peak_week(weekly_df, col)      # 历史最高值所在周
calc_posting_consistency(profile)   # 发布频率的稳定性（标准差）
```

---

## analysis/scoring.py

**职责：** 综合多项指标，给 UP 主的成长潜力打分。

```
compute_score(profile, weekly_df)
  ├── 播放量趋势得分（近期增长斜率）
  ├── 互动率得分（engagement / view）
  ├── 更新稳定性得分（发布间隔方差）
  └── 加权求和，返回 0~100 分

score_breakdown(profile, weekly_df)
  └── 返回各维度分项得分 dict，用于可视化展示
```

---

## analysis/trend.py

**职责：** 对历史时序数据做趋势分析，识别增长 / 平台期 / 下滑阶段。

```
detect_trend_phase(series)
  ├── 线性回归斜率判断整体趋势方向
  └── 返回 "growing" / "stable" / "declining"

find_breakpoints(series)
  └── 检测突变点（如某期视频爆火导致粉丝跳涨）

moving_average(series, window)
  └── 简单移动均值平滑，去除周度噪声
```

---

## analysis/forecast_result.py

**职责：** 【新增】将 predictor 的预测 DataFrame 解析为人类可读的结构化摘要。

```
parse_forecast(forecast_df, history_df)
  ├── 计算预测值相对历史均值的变化幅度
  ├── 标记显著增长 / 下滑的目标（超过阈值）
  └── 返回结构化摘要 dict

format_forecast_summary(summary_dict)
  └── 格式化为可打印的文字描述，供 CLI 输出或报告使用
```

---

## visualization/trend_chart.py

**职责：** 绘制 UP 主历史指标的时序折线图。

```
plot_weekly_trends(weekly_df, targets, save_path=None)
  ├── 子图分别展示 view / follower_gain / engagement / video_count
  ├── 标注历史最高点
  └── 保存为 PNG 或直接 show()

plot_correlation_heatmap(weekly_df)
  └── 四个指标之间的相关性热力图
```

---

## visualization/forecast_chart.py

**职责：** 【新增】绘制历史数据 + 未来预测的对比图，含置信区间色带。

```
plot_forecast(history_df, forecast_df, target, interval_df=None, save_path=None)
  ├── 历史段：实线
  ├── 预测段：虚线 + 不同颜色
  ├── 置信区间：半透明色带（若传入 interval_df）
  └── 竖线分隔历史与预测边界

plot_all_forecasts(history_df, forecast_df)
  └── 四个目标指标一次性绘制为 2×2 子图布局
```

---

## pipeline/run_pipeline.py

**职责：** 【新增】统一调度全链路，替代 main.py 中的流程控制逻辑。

```
run(mid, horizon=4, train=True, use_cache=True)
  ├── Step 1  fetch_uploader_data(mid)         数据采集
  ├── Step 2  load/save profile cache          本地 JSON 缓存读写
  ├── Step 3  build_feature_matrix(profile)    特征构造
  ├── Step 4  train_all_targets(df)            模型训练（或跳过加载已有）
  ├── Step 5  print_evaluation_report()        回测评估
  ├── Step 6  predictor.predict(df, horizon)   滚动预测
  └── Step 7  保存结果至 data/processed/forecast_{mid}.csv

CLI 参数：
  --mid        UP 主 UID（必填）
  --horizon    预测未来几周，默认 4
  --no-train   跳过训练，复用已有模型
  --no-cache   忽略本地缓存，强制重新拉取
```

---

## utils/file_utils.py

**职责：** 通用文件读写工具，统一处理路径和序列化格式。

```
save_json(data, path)         # dict → JSON 文件，自动创建目录
load_json(path)               # JSON 文件 → dict，文件不存在返回 None
save_dataframe(df, path)      # DataFrame → CSV / Parquet（按后缀自动选择）
load_dataframe(path)          # CSV / Parquet → DataFrame
ensure_dir(path)              # 确保目录存在，不存在则创建
```

---

## utils/logger.py

**职责：** 统一日志配置，所有模块通过此处获取 logger，不直接使用 print。

```
get_logger(name)
  ├── 返回配置好的 logging.Logger 实例
  ├── 同时输出到控制台（INFO 级别）
  └── 写入 logs/run_{date}.log 文件（DEBUG 级别）
```

---

## config/settings.py

**职责：** 集中管理所有可配置参数，各模块从此处 import，不硬编码。

```python
# 路径配置
DATA_DIR   = Path("data")
MODEL_DIR  = DATA_DIR / "processed" / "models"
CACHE_DIR  = DATA_DIR / "cache"
LOG_DIR    = Path("logs")

# 特征工程参数
LAG_WEEKS    = [1, 2, 3, 4, 8]
ROLLING_WINS = [3, 8]

# 模型超参数
XGB_PARAMS = {
    "n_estimators":     300,
    "learning_rate":    0.05,
    "max_depth":        4,
    "subsample":        0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 3,
    "random_state":     42,
}

# 预测配置
DEFAULT_HORIZON  = 4       # 默认预测周数
BACKTEST_WEEKS   = 8       # 回测测试集周数
CONFIDENCE_ALPHA = 0.1     # 置信区间 alpha（0.1 → 80% 区间）
```

---

## tests/

**职责：** 各模块单元测试，后期补充。建议优先覆盖以下三处（最容易出 bug）：

| 测试文件 | 测试重点 |
|----------|----------|
| `test_feature_builder.py` | 缺失周补全、滞后特征计算是否正确 |
| `test_predictor.py` | 滚动预测是否真正用预测值而非历史值 |
| `test_pipeline.py` | 端到端 mock 数据流转是否完整 |

---

## requirements.txt

```
bilibili-api-python>=16.0   # B 站数据采集
pandas>=2.0                 # 数据处理 & 时序聚合
numpy>=1.26                 # 数值计算
xgboost>=2.0                # 预测模型
scikit-learn>=1.4           # TimeSeriesSplit、误差指标
matplotlib>=3.8             # 可视化
seaborn>=0.13               # 热力图等统计图表
```

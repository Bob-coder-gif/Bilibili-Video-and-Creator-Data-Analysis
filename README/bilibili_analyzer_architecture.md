# bilibili_analyzer 项目架构文档

> 目标：基于 UP 主历史数据，使用 XGBoost 对播放量、粉丝增长、点赞/投币/收藏、发布频率进行按周预测。

---

## 目录结构总览

```
bilibili_analyzer/
│
├── app/
│   └── main.py
│
├── crawler/
│   ├── bilibili_client.py
│   └── fetch_videos.py
│
├── data/
│   ├── raw/
│   ├── processed/
│   │   └── models/                  ← 训练好的模型文件（.ubj）
│   └── cache/                       ← UP主数据本地缓存（.json）
│
├── features/                        ← 【新增】特征工程层
│   ├── __init__.py
│   └── feature_builder.py
│
├── models/
│   ├── __init__.py
│   ├── video.py                     ← 数据结构定义
│   └── ml/                          ← 【新增】机器学习模型层
│       ├── __init__.py
│       ├── trainer.py
│       ├── predictor.py
│       └── evaluator.py
│
├── analysis/
│   ├── metrics.py
│   ├── scoring.py
│   ├── trend.py
│   └── forecast_result.py           ← 【新增】预测结果解析
│
├── visualization/
│   ├── trend_chart.py
│   └── forecast_chart.py            ← 【新增】历史 vs 预测对比图
│
├── pipeline/                        ← 【新增】流程编排层
│   ├── __init__.py
│   └── run_pipeline.py
│
├── utils/
│   ├── file_utils.py
│   └── logger.py
│
├── config/
│   └── settings.py
│
├── tests/
│
├── requirements.txt
└── README.md
```

---

## 各模块说明

### `models/video.py` — 数据结构

项目中所有模块共享的数据契约，定义三个核心类：

| 类名 | 职责 |
|------|------|
| `VideoStats` | 单条视频统计快照（播放/点赞/投币/收藏/弹幕等） |
| `Video` | 单个视频完整信息，含 `pubdate_week` 属性（周粒度聚合用） |
| `UploaderProfile` | UP 主信息 + 视频列表 + 粉丝历史快照 |

---

### `crawler/` — 数据采集

| 文件 | 职责 |
|------|------|
| `bilibili_client.py` | HTTP 请求封装、鉴权、限流重试 |
| `fetch_videos.py` | 业务逻辑：分页拉取视频列表、字段提取、转换为 `Video` 对象 |

> 数据来源：调用 `bilibili-api-python` 第三方库。

---

### `features/feature_builder.py` — 特征工程 【核心新增】

将原始 `UploaderProfile` 转换为 XGBoost 可用的特征矩阵，五步流水线：

| 步骤 | 函数 | 说明 |
|------|------|------|
| 1 | `build_weekly_base()` | 按自然周聚合视频指标，补全缺失周（填 0） |
| 2 | `attach_follower_gain()` | 粉丝快照差分 → 周增量 |
| 3 | `add_lag_features()` | 滞后特征，窗口：1/2/3/4/8 周 |
| 4 | `add_rolling_features()` | 滚动均值 & 标准差，窗口：3/8 周 |
| 5 | `add_time_features()` | 周序号、月份、季度、正余弦编码 |

主入口：`build_feature_matrix(profile)` → 返回 `pd.DataFrame`

---

### `models/ml/` — 预测模型 【核心新增】

#### `trainer.py`

- 四个预测目标各自独立训练一个 XGBoost（`view` / `follower_gain` / `engagement` / `video_count`）
- 使用 `TimeSeriesSplit` 做时序交叉验证（禁止随机 split）
- 全量重训后保存为 `.ubj` 格式至 `data/processed/models/`

#### `predictor.py`

- 加载已训练模型，执行**自回归滚动预测**
- 每次预测下一周 → 将预测值写回历史 → 预测下下周
- 主方法：`BilibiliPredictor.predict(history_df, horizon=4)`

#### `evaluator.py`

| 函数 | 说明 |
|------|------|
| `backtest()` | 回测误差：MAE / MAPE / RMSE |
| `feature_importance()` | 各目标模型 Top-N 重要特征（gain） |
| `predict_with_interval()` | 分位数回归置信区间（P10 ~ P90） |
| `print_evaluation_report()` | 汇总打印回测结果 + 特征重要性 |

---

### `pipeline/run_pipeline.py` — 流程编排 【核心新增】

替代 `app/main.py`，统一调度全链路：

```
数据采集 → 本地缓存 → 特征构造 → 模型训练 → 回测评估 → 滚动预测 → 结果输出
```

CLI 用法：
```bash
# 完整运行（训练 + 预测）
python -m pipeline.run_pipeline --mid <UP主UID> --horizon 4

# 复用已有模型（跳过训练）
python -m pipeline.run_pipeline --mid <UP主UID> --no-train

# 忽略缓存，强制重新拉取
python -m pipeline.run_pipeline --mid <UP主UID> --no-cache
```

---

### `analysis/` — 分析层（原有 + 扩展）

| 文件 | 职责 |
|------|------|
| `metrics.py` | 基础指标计算（均值、增长率等） |
| `scoring.py` | UP 主综合评分逻辑 |
| `trend.py` | 历史趋势分析 |
| `forecast_result.py` | 【新增】解析预测输出，生成结构化摘要 |

---

### `visualization/` — 可视化（原有 + 扩展）

| 文件 | 职责 |
|------|------|
| `trend_chart.py` | 历史指标折线图 |
| `forecast_chart.py` | 【新增】历史 + 预测对比图（含置信区间色带） |

---

### `config/settings.py` — 配置中心

统一管理以下参数，各模块从此处读取，不硬编码：

```python
# XGBoost 超参数
XGB_PARAMS = { "n_estimators": 300, "learning_rate": 0.05, ... }

# 特征工程参数
LAG_WEEKS    = [1, 2, 3, 4, 8]
ROLLING_WINS = [3, 8]

# 路径
DATA_DIR      = Path("data")
MODEL_DIR     = DATA_DIR / "processed" / "models"
CACHE_DIR     = DATA_DIR / "cache"
```

---

## 数据流向

```
B站 API
  │
  ▼
crawler/fetch_videos.py          拉取原始视频列表
  │
  ▼
data/cache/                      JSON 缓存，避免重复请求
  │
  ▼
features/feature_builder.py      构造特征矩阵（周粒度 DataFrame）
  │
  ├─▶ models/ml/trainer.py       训练 XGBoost（4个目标，各自独立）
  │         │
  │         ▼
  │   data/processed/models/     持久化模型文件（.ubj）
  │
  └─▶ models/ml/predictor.py     加载模型，自回归滚动预测 N 周
            │
            ▼
      models/ml/evaluator.py     回测误差 + 特征重要性
            │
            ▼
      visualization/             趋势图 + 预测对比图
```

---

## 技术依赖

| 库 | 用途 |
|----|------|
| `bilibili-api-python` | B 站数据采集 |
| `pandas` | 数据处理 & 时序聚合 |
| `numpy` | 数值计算 |
| `xgboost` | 预测模型 |
| `scikit-learn` | TimeSeriesSplit、误差指标 |
| `matplotlib` / `seaborn` | 可视化 |

---

## 扩展方向

| 需求 | 建议做法 |
|------|----------|
| 接入多个 UP 主批量分析 | `pipeline/batch_pipeline.py` |
| 定时自动抓取 | `scheduler/` + APScheduler |
| 接入数据库 | `db/` 层，替换 JSON 缓存 |
| 对比多 UP 主 | `analysis/comparison.py` |
| Web 展示 | `app/` 改为 FastAPI 服务 |

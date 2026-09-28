# Bilibili 视频舆情分析 —— 项目架构文档

> 输入一个视频 BV 号，自动爬取评论（含楼中楼回复）与弹幕，完成中文情绪分析、
> 关键词提取、话题聚类与舆情预警，并通过网页提交任务、查看分析结果与历史趋势。

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 安装 Playwright 浏览器内核（首次必做）
playwright install

# 3. 启动网页服务（必须在项目根目录用 -m 方式运行）
python -m app.web
# 浏览器打开 http://127.0.0.1:5000
```

**首次运行要做的两件事：**

1. **登录 B 站**：启动服务时如果没有登录态，会先弹出浏览器，登录后回到终端按回车，
   登录态保存到 `bilibili_data/bilibili_state.json`，之后不再需要登录。
   登录态过期后删除该文件重新启动即可。
2. **下载模型**：情绪模型和 BERTopic 的向量模型来自 HuggingFace。项目默认
   `HF_OFFLINE = True`（只用本地缓存）。第一次使用时把 `config/config.py` 里的
   `HF_OFFLINE` 改成 `False`，跑一个任务让模型通过国内镜像 `hf-mirror.com` 下载，
   下载完成后改回 `True`。不需要挂梯子。

---

## 目录结构

```
bilibili_analyse_project/
│
├── app/                          Web 服务与任务调度
│   ├── web.py                    Flask 后端 + 内嵌前端页面（项目入口）
│   └── task_runner.py            任务队列（单 worker 串行执行）
│
├── crawler/                      数据采集层
│   ├── bilibili_state.py         登录态管理 + 浏览器启动
│   ├── fetch_comments.py         爬取评论（含回复）
│   ├── fetch_danmu.py            爬取弹幕
│   └── get_info_from_browser.py  获取视频信息 + 统计数据 stat（带缓存与浏览器兜底）
│
├── analyzer/                     分析层
│   ├── bert_analyzer.py          BERT 中文情绪分析
│   ├── keyword_extractor.py      关键词 / 词频 / 停用词
│   ├── topic_analyzer.py         话题聚类（BERTopic + jieba）
│   ├── video_stats.py            视频统计快照 + 历史 + 趋势图
│   └── warning_detector.py       舆情预警检测
│
├── pipeline/                     流程编排层
│   ├── crawler_pipeline.py       采集阶段
│   ├── sentiment_pipeline.py     情绪分析阶段
│   └── pipeline_data_analysis.py 统计 / 预警 / 话题阶段
│
├── visualization/                可视化层
│   ├── danmu_vis.py              弹幕词云 / 密度图 / 高频弹幕
│   └── report.py                 情绪分析报告（JSON）
│
├── utils/                        工具层
│   ├── http_utils.py             B 站接口请求（UA/Cookie/风控识别/异常类型）
│   ├── file_utils.py             产物保存 + 统一目录拼接（文件名安全处理）
│   ├── loader.py                 评论 / 弹幕 JSON → DataFrame
│   ├── cleaner.py                文本清洗
│   ├── plot_utils.py             matplotlib 后端 + 中文字体
│   └── log_utils.py              日志 + 结构化事件记录
│
├── config/                       配置层
│   ├── config.py                 全局配置（路径 / 阈值 / 模型名 / 浏览器等）
│   └── hf_setup.py               HuggingFace 国内镜像 + 离线设置
│
├── README/                       项目文档
├── data/                         运行产物（自动生成，已 gitignore）
├── logs/                         运行日志（自动生成，已 gitignore）
├── bilibili_data/                登录态 Cookie（自动生成，已 gitignore）
└── requirements.txt
```

---

## 整体数据流

```
用户在网页输入 BV 号
        │
        ▼
  app/web.py  ──提交任务──▶  app/task_runner.py（进队列，单 worker 串行取出）
        │                              │
        │                              ▼
        │             三段式 pipeline，通过 task 字典传递数据
        │        ┌─────────────────────┼─────────────────────┐
        │        ▼                     ▼                     ▼
        │  crawler_pipeline    sentiment_pipeline    pipeline_data_analysis
        │  评论+回复+弹幕        清洗+BERT情绪          统计快照+趋势图
        │  视频信息+弹幕图       关键词+报告            预警+话题聚类
        │        │                     │                     │
        │        ▼                     ▼                     ▼
        │     data/raw            data/report          data/analysis
        │   data/processed                              data/topic
        │
        ▼
  前端每 2 秒轮询 /api/task  ◀── worker 通过 progress 回调实时写进度
        │
        ▼
  完成后跳转 /video/<bv_id> 查看详情
  （情绪分布 / 趋势图 / 词云 / 密度图 / 高频弹幕 / 预警 / 话题 / 抓取历史）
```

---

## 三个阶段如何串联

```python
task = crawler_pipeline(bv_id, progress)       # 采集
task = sentiment_pipeline(task, progress)      # 情绪分析
task = pipeline_data_analysis(task, progress)  # 统计 / 预警 / 话题
```

三个阶段之间只通过 `task` 字典传递数据，不使用全局变量。

- **crawler_pipeline**：生成本次任务统一的 `time_str`，爬评论（打开视频页时顺便
  缓存视频信息）→ 获取视频信息和 stat → 爬弹幕 → 生成三张弹幕图。
- **sentiment_pipeline**：加载评论（主评论和回复展开成一张表）和弹幕 → 清洗 →
  BERT 情绪分析 → 关键词 / 词频 → 生成 `report.json`；再把清洗后的评论文本、
  情绪标签、情绪计数写回 `task`，供下一阶段使用。
- **pipeline_data_analysis**：保存统计快照并追加到历史 → 把情绪计数补写进这条
  历史记录 → 基于完整历史做预警 → BERTopic 话题聚类。这三步顺序不能调换。

`progress` 是可选的进度回调，由 `task_runner` 传入，pipeline 在关键节点调用
`progress(stage, message)`，前端据此显示"正在爬取评论…已 N 条"等实时进度。

---

## 关键设计

### 任务队列：单 worker 串行

- 用标准库 `queue.Queue` + **一个** worker 线程，不依赖 Redis。
- 串行是刻意的：爬虫用真实浏览器访问 B 站，多任务并发就是多个浏览器用同一登录态、
  同一 IP 高频请求，更容易触发风控；BERT 推理也会互相抢 CPU。
- 支持运行中继续提交（排队）、取消排队任务、清空队列；正在运行的任务不能中途取消
  （避免留下半开的浏览器和写了一半的文件）。
- 已结束的任务在内存中保留最近 100 个。

### 反爬与风控处理

- 评论不是自己拼接口请求，而是让真实浏览器打开页面、滚动加载，同时拦截浏览器自己
  发出的评论 API 响应，自动发现接口地址。
- 视频信息优先从页面的 `window.__INITIAL_STATE__` 读取并缓存，同一任务不重复请求
  view 接口；接口被风控（HTTP 412）时自动改用浏览器方式获取。
- 回复请求之间随机间隔 0.5~1.2 秒；一旦遇到风控立即停止抓剩余回复，保留已抓到的数据。
- 所有 `requests` 请求统一走 `utils/http_utils.py`，按异常类型区分失败原因：

  | 异常 | 前端提示 |
  |------|---------|
  | `BiliRiskControlError` | 触发风控，稍后再试或换网络 |
  | `BiliNotFoundError` | 视频不存在 / 已删除 / 不可见 |
  | `BiliLoginRequiredError` | 未登录，需重启服务登录 |
  | `BiliRequestError` | 其他接口请求失败 |

### 情绪三分类

所用模型是二分类（正 / 负）。项目把模型输出统一换算成"正向概率"（`bert_score`），
再按阈值分三类：`>= 0.6` 正向，`<= 0.4` 负向，中间为中性（模型拿不准的文本）。
阈值在 `config.POS_THRESHOLD / NEG_THRESHOLD` 调整。

### 舆情预警

基于同一视频的多次抓取历史，检测三类情况（阈值见 config）：
负向评论占比过高、负向占比较上次骤升、播放量较上次暴增。

---

## 输出目录结构

同一次任务的产物落在同一个 `{bv_id}/{time_str}/` 目录下；跨次累积的文件
（历史、趋势图）直接放在 `{bv_id}/` 下。`uname`、`title` 会把 Windows 文件名
非法字符（`\ / : * ? " < > |`）替换为 `_`。

```
data/raw/comments/{uname}/{title}/{bv_id}/{time_str}/comments.json
data/raw/danmu/{uname}/{title}/{bv_id}/{time_str}/danmu.json

data/report/{uname}/{title}/{bv_id}/{time_str}/
    ├── comments_annotated.json    带情绪标签的评论（含回复）
    ├── comments_summary.json      评论情绪计数
    ├── danmaku_annotated.json
    ├── danmaku_summary.json
    ├── report.json                情绪报告（分布 / 按日趋势 / 弹幕时间轴 / 关键词 / 高赞评论）
    └── word_freq.json             词频

data/analysis/{uname}/{title}/{bv_id}/
    ├── history.json               跨次累积的统计历史
    ├── trend.png                  趋势图（至少 2 次抓取后生成）
    └── {time_str}/
          ├── stats_analysis.json  本次统计快照
          └── warnings.json        本次预警

data/topic/{uname}/{title}/{bv_id}/{time_str}/topics.json

data/processed/danmu/{uname}/{title}/{bv_id}/{time_str}/
    ├── danmu_wordcloud.png
    ├── danmu_density.png
    └── top_danmu.png

logs/debug/{date}.log              全量 DEBUG 日志
logs/runtime/{date}.jsonl          结构化运行事件（每行一个 JSON）
```

---

## 技术依赖

| 库 | 用途 |
|----|------|
| `playwright` | 真实浏览器加载页面、拦截评论 API、兜底获取视频信息 |
| `requests` | 弹幕 / 视频信息接口请求 |
| `flask` | 网页后端与任务接口 |
| `transformers` / `torch` | BERT 中文情绪分析 |
| `bertopic` / `sentence-transformers` / `umap-learn` / `hdbscan` | 话题聚类 |
| `scikit-learn` | 配合 jieba 为 BERTopic 提取中文话题词 |
| `jieba` / `wordcloud` | 中文分词、关键词、词云 |
| `pandas` / `numpy` | 数据处理 |
| `matplotlib` | 趋势图、弹幕图 |

---

## 已知限制

- **回复只抓第一页**：每条主评论下只抓前 10 条回复。抓全部回复会大幅增加请求数，
  更容易触发风控。
- **弹幕是实时弹幕池**：`list.so` 接口只返回当前弹幕池（有上限，视视频时长从几百到几千条），
  不是全部历史弹幕；多 P 视频只抓第 1 P。
- **任务状态在内存里**：服务重启后排队中和运行中的任务都会丢失（已落盘的结果不受影响）。
- **历史按"UP 主名/标题"归档**：UP 主改名或视频改标题后，新数据会进入新目录，
  趋势图会从头开始累积。
- **仅本机使用**：Flask 开发服务器，只监听 127.0.0.1。

---

## 未来扩展方向（当前未实现）

| 方向 | 说明 |
|------|------|
| UP 主数据预测 | 基于历史统计数据，用 XGBoost 等模型预测播放量 / 粉丝增长 |
| 全量历史弹幕 | 接入按日期分页的历史弹幕接口（protobuf `seg.so`） |
| 多视频批量分析 | 一次提交一批 BV 号，统一分析对比 |
| 定时自动抓取 | 对同一视频定时多次抓取，形成更密的趋势 / 预警曲线 |
| 部署上线 | 改用 WSGI 服务器，任务状态持久化 |

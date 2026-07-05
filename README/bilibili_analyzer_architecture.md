# Bilibili 视频舆情分析 —— 项目架构文档

> 目标：输入一个视频 BV 号，自动爬取其评论与弹幕，进行中文情绪分析、
> 话题聚类与舆情预警，并通过网页界面提交任务、查看分析结果与历史趋势。

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 安装 Playwright 浏览器内核（首次必做）
playwright install

# 3. 启动网页服务
python -m app.web
# 浏览器打开 http://127.0.0.1:5000
```

> 首次运行会弹出浏览器要求登录 B 站账号（保存登录态到 `bilibili_data/`），
> 之后不再需要重复登录。

---

## 目录结构

```
bilibili_analyse_project/
│
├── app/                          Web 服务与任务调度
│   ├── main.py                   命令行入口（历史遗留，日常用 web.py）
│   ├── web.py                    Flask 网页后端 + 前端页面
│   └── task_runner.py            任务队列（单 worker 串行执行）
│
├── crawler/                      数据采集层
│   ├── bilibili_state.py         登录态管理 + 浏览器启动
│   ├── fetch_comments.py         爬取评论（含回复）
│   ├── fetch_danmu.py            爬取弹幕
│   └── get_info_from_browser.py  获取视频信息 + 统计数据(stat)
│
├── analyzer/                     分析层
│   ├── bert_analyzer.py          BERT 中文情绪分析
│   ├── keyword_extractor.py      关键词 / 词频提取
│   ├── topic_analyzer.py         话题聚类（BERTopic）
│   ├── video_stats.py            视频统计数据 + 趋势图
│   └── warning_detector.py       舆情预警检测
│
├── pipeline/                     流程编排层
│   ├── crawler_pipeline.py       采集阶段
│   ├── sentiment_pipeline.py     情绪分析阶段
│   └── pipeline_data_analysis.py 统计/预警/话题阶段
│
├── visualization/               可视化层
│   ├── danmu_vis.py              弹幕词云 / 密度图 / 高频词条
│   └── report.py                 情绪分析报告(JSON)
│
├── utils/                       工具层
│   ├── cleaner.py                文本清洗
│   ├── loader.py                 读取评论/弹幕 JSON 为 DataFrame
│   ├── file_utils.py             文件保存(评论/弹幕/报告/词频等)
│   └── log_utils.py              统一日志 + 结构化事件记录
│
├── config/                     配置层
│   ├── config.py                 全局配置(路径/阈值/模型名等)
│   └── hf_setup.py               HuggingFace 国内镜像 + 离线设置
│
├── data/                       运行产物(自动生成)
│   ├── raw/                      原始评论/弹幕 JSON
│   ├── report/                  情绪分析报告 + 标注结果
│   ├── analysis/                 统计快照 + 历史 + 趋势图 + 预警
│   ├── topic/                    话题聚类结果
│   └── processed/               弹幕可视化图片
│
├── bilibili_data/              登录态(cookie)
├── logs/                       运行日志
├── requirements.txt
└── README.md
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
        │                     ┌─────────────────────────────┐
        │                     │  三段式 pipeline（task 传递） │
        │                     └─────────────────────────────┘
        │                              │
        │        ┌─────────────────────┼─────────────────────┐
        │        ▼                     ▼                     ▼
        │  crawler_pipeline    sentiment_pipeline    pipeline_data_analysis
        │  爬评论+弹幕+可视化    BERT情绪+关键词+报告   统计+趋势+预警+话题聚类
        │        │                     │                     │
        │        ▼                     ▼                     ▼
        │     data/raw          data/report          data/analysis
        │   data/processed                            data/topic
        │
        ▼
  轮询进度 /api/task  ◀──worker 实时回写进度──┘
        │
        ▼
  完成后跳转 /video/<bv_id> 查看详情
  （情绪分布 / 趋势图 / 词云 / 密度 / 高频弹幕 / 预警 / 话题 / 历史）
```

---

## 三个阶段（pipeline）如何串联

三个 pipeline 通过一个 `task` 字典依次传递，不使用全局变量，保证并发安全：

```python
task = crawler_pipeline(bv_id, progress)          # 采集
task = sentiment_pipeline(task, progress)          # 情绪分析
task = pipeline_data_analysis(task, progress)      # 统计/预警/话题
```

- **crawler_pipeline**：爬评论、爬弹幕、生成弹幕可视化图；在 `task` 中生成
  统一的 `time_str`（本次任务时间目录名），供后续所有产物落在同一目录下。
- **sentiment_pipeline**：加载 → 清洗 → BERT 情绪分析 → 关键词 → 生成报告；
  并把"清洗后评论文本、情绪标签、情绪摘要"写回 `task`，供下游话题聚类/预警使用。
- **pipeline_data_analysis**：保存视频统计快照、累积历史、画趋势图；做舆情预警；
  做 BERTopic 话题聚类。

`progress` 是一个可选的进度回调：命令行单独运行时为 `None`（跳过），
网页任务运行时由 `task_runner` 传入，用于把"正在爬评论 N 条 / 正在情绪分析 …"
等实时进度回写，供前端轮询显示。

---

## 任务队列设计（app/task_runner.py）

- 使用 Python 标准库 `queue.Queue` + **单个** worker 线程，不依赖 Redis。
- **单 worker 串行**是刻意设计：爬虫用真实浏览器(Playwright)爬 B 站，
  并发多个任务 = 多个浏览器用同一登录态高频请求，更易触发风控；串行则
  任意时刻只有一路在爬，最接近正常用户行为，也避免 BERT 争抢资源。
- 支持运行时继续提交任务（排队）、取消排队中的任务、清空队列；
  正在运行的任务不可中途取消（避免留下半个浏览器进程/半个文件）。
- 局限：任务状态存于内存，程序重启会丢失。对单机使用无影响。

---

## 输出目录结构约定

同一次任务的全部产物落在同一个 `{bv_id}/{time_str}/` 目录下，
跨次累积的文件（历史、趋势图）不带时间层，直接在 `{bv_id}/` 下：

```
data/report/{uname}/{title}/{bv_id}/{time_str}/
    ├── comments_annotated.json    带情绪标签的评论
    ├── comments_summary.json      情绪标签计数摘要
    ├── danmaku_annotated.json
    ├── danmaku_summary.json
    ├── report.json                情绪分析报告
    └── word_freq.json             词频

data/analysis/{uname}/{title}/{bv_id}/
    ├── history.json               跨次累积的统计历史（不带时间）
    ├── trend.png                  趋势图（不带时间）
    └── {time_str}/
          ├── stats_analysis.json  本次统计快照
          └── warnings.json        本次预警

data/topic/{uname}/{title}/{bv_id}/{time_str}/topics.json
data/processed/danmu/{uname}/{title}/{bv_id}/{time_str}/
    ├── danmu_wordcloud.png
    ├── danmu_density.png
    └── top_danmu.png
```

---

## 技术依赖

| 库 | 用途 |
|----|------|
| `playwright` | 真实浏览器爬取评论/弹幕，拦截 B 站 API 响应 |
| `curl_cffi` | 高速分页请求（反爬 impersonate） |
| `flask` | 网页后端 + 任务提交/进度/详情接口 |
| `transformers` / `torch` | BERT 中文情绪分析 |
| `bertopic` / `sentence-transformers` | 话题聚类及其文本向量化 |
| `jieba` / `wordcloud` | 中文分词与词云 |
| `pandas` / `numpy` | 数据处理 |
| `matplotlib` | 趋势图、弹幕密度图 |

> 国内网络：情绪与话题模型来自 HuggingFace，项目已在代码中自动设置
> 国内镜像 `hf-mirror.com` 并优先使用本地缓存（见 `config/hf_setup.py`
> 与 `analyzer/bert_analyzer.py`），无需挂梯子。

---

## 未来扩展方向

以下为后续可能的方向，**当前尚未实现**：

| 方向 | 说明 |
|------|------|
| UP 主数据预测 | 基于历史统计数据，用 XGBoost 等模型预测未来播放量/粉丝增长（项目最初设想，因复杂度暂缓） |
| 全量历史弹幕 | 当前只抓实时弹幕接口，可扩展按天分页的历史弹幕接口 |
| 多视频批量分析 | 批量提交一批 BV 号统一分析对比 |
| 定时自动抓取 | 定时对同一视频多次抓取，形成更密的趋势/预警曲线 |
| 部署上线 | 从本地开发服务器改为正式部署（需 WSGI 服务器 + 服务器环境） |
```
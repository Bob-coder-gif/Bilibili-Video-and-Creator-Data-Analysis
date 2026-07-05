# 文件职责说明

> 逐个说明每个 Python 文件的职责、关键函数与依赖关系。
> 配合《项目架构文档.md》一起看。

---

## app/ —— Web 服务与任务调度

### app/web.py
Flask 网页后端，项目的实际入口（`python -m app.web`）。同时内嵌前端页面(HTML/JS)。

- 页面：`/`（首页：提交 BV 号 + 进度条 + 队列面板 + 历史列表）、
  `/video/<bv_id>`（详情页）。
- 接口：
  - `POST /api/analyze` 提交任务，立刻返回 task_id（不阻塞）
  - `GET  /api/task/<task_id>` 轮询任务进度
  - `GET  /api/queue` 队列概览（正在跑 + 排队列表）
  - `POST /api/task/<task_id>/cancel` 取消排队中的任务
  - `POST /api/queue/clear` 清空队列（仅排队中的）
  - `GET  /api/history` 已分析视频列表
  - `GET  /api/history/<bv_id>` 某视频详情（历史/预警/话题）
  - `GET  /api/image/<bv_id>/<kind>` 返回图片(趋势/词云/密度/高频弹幕)
- 顶部设置 HuggingFace 国内镜像 + 离线环境变量（在所有 import 之前）。
- 过滤 werkzeug 逐条请求日志，保留启动横幅与业务日志。

### app/task_runner.py
任务队列，`queue.Queue` + 单 worker 线程串行执行。

- `submit_task(bv_id)` 入队，返回 task_id
- `get_task(task_id)` 查进度（含"前面还有几个"）
- `get_queue_overview()` 队列概览
- `cancel_task(task_id)` / `clear_queue()` 取消/清空排队任务
- worker 依次调用三个 pipeline，并把进度实时写回内存任务表。

### app/main.py
命令行入口（历史遗留）。日常使用已由 `web.py` 取代，保留用于命令行调试。

---

## crawler/ —— 数据采集层

### crawler/bilibili_state.py
登录态管理 + 浏览器启动。

- `save_login_state()` 首次运行时弹出可见浏览器，手动登录后保存 cookie。
- `launch_browser(p, headless)` 按 config 选择浏览器引擎启动，chromium 下
  使用 `--headless=new`（新版无头模式，不易被 B 站识别为爬虫）。

### crawler/fetch_comments.py
爬取评论（含楼中楼回复）。

- `fetch_comments(bv_id, max_count, progress)`：打开视频页 → 滚动触发评论
  分页 → 拦截 B 站评论 API 响应收集数据 → 统一抓取回复。
- 打开页面后等待网络空闲并放宽等待，附带整页重试，解决"连续跑多个任务
  时部分任务爬到 0 条评论"的问题。
- 通过 `progress` 回调实时汇报已爬取条数。

### crawler/fetch_danmu.py
爬取弹幕。

- `fetch_danmu(bv_id)`：先 `get_cid(bv_id)` 取视频的 cid，再请求弹幕 XML
  接口，经 `parse_danmu(xml)` 把 XML 解析成结构化弹幕列表（含出现时间、内容等）。
- 抓取的是 B 站实时弹幕接口，返回列表供后续可视化与分析。

### crawler/get_info_from_browser.py
获取视频元信息与统计数据。

- `get_video_info(bv_id)` 返回 `(video_info, stat)`：
  `video_info = [uid, uname, title]`，`stat` 为播放/点赞/投币/收藏/
  分享/弹幕/评论等计数字典。

---

## analyzer/ —— 分析层

### analyzer/bert_analyzer.py
BERT 中文情绪分析。

- `analyze(df, cfg)`：对 `text_clean` 列做情绪分类，新增 `bert_score` /
  `bert_label`（正向/负向/中性）两列。
- 模型 `uer/roberta-base-finetuned-jd-binary-chinese`，模块级单例避免重复加载。
- import transformers 前设置 HF 镜像 + 离线；加载模型用 `local_files_only=True`
  强制走本地缓存，彻底规避国内联网超时。

### analyzer/keyword_extractor.py
关键词与词频提取（基于 jieba）。

- `extract_keywords(df, cfg, label_filter, label_col)` 用 jieba TF-IDF 提取关键词，
  可按情绪标签(正向/负向)筛选。
- `word_frequency(df, cfg)` 用 jieba 分词做词频统计，补充 TF-IDF 之外的视角。
- 内置一份 B 站场景停用词表（"哈哈哈"/"666"/"up主"/"弹幕"等无意义词），
  也可通过 `cfg.STOPWORDS_FILE` 外挂扩充。

### analyzer/topic_analyzer.py
话题聚类（BERTopic）。

- `run_topic_analysis(texts, bv_id, video_info, labels, time_str)`：
  对评论文本聚类出话题，输出关键词/规模/情绪分布/示例。
- 优雅降级：评论数少于 `TOPIC_MIN_DOCS` 或未安装 BERTopic 时跳过、返回 None，
  不影响主流程。

### analyzer/video_stats.py
视频统计数据保存、历史累积、趋势图生成。

- `save_video_stats(bv_id, video_info, stat, time_str)`：保存本次快照、
  追加进 history.json、数据点足够时重绘趋势图。
- `get_history(bv_id, video_info)` 读取累积历史。
- 自动检测中文字体，趋势图分两个子图（播放/弹幕/评论 与 点赞/投币/收藏/分享）。

### analyzer/warning_detector.py
舆情预警检测。

- `detect_warnings(history)`：三类预警——负向占比过高、负向占比骤升、
  播放量暴增。阈值可在 config 调整。
- `record_sentiment_summary(...)` 把情绪摘要补写进历史最新记录。
- `save_warnings(...)` 落盘预警结果。

---

## pipeline/ —— 流程编排层

三个阶段通过 `task` 字典依次传递，`progress` 为可选进度回调。

### pipeline/crawler_pipeline.py
采集阶段。爬评论 → 爬弹幕 → 弹幕可视化。生成本次任务统一的 `time_str`，
返回包含 bv_id/video_info/comments/danmus/路径/stat/time_str 的 task。

### pipeline/sentiment_pipeline.py
情绪分析阶段。加载 → 清洗 → BERT 情绪分析 → 关键词 → 生成报告。
并把"清洗后评论文本、情绪标签、情绪摘要"写回 task，供下游话题聚类/预警使用。

### pipeline/pipeline_data_analysis.py
统计/预警/话题阶段。保存统计快照+趋势图 → 补写情绪摘要+预警检测 →
BERTopic 话题聚类。三步顺序不可乱（预警依赖先落盘的统计+情绪摘要）。

---

## visualization/ —— 可视化层

### visualization/danmu_vis.py
弹幕可视化，三张图：

- `plot_top_danmu(...)` 高频弹幕词条柱状图
- `plot_danmu_density(...)` 弹幕时间轴密度图
- `plot_danmu_wordcloud(...)` 弹幕词云
- 保存到 `data/processed/danmu/.../{bv_id}/{time_str}/`。

### visualization/report.py
情绪分析报告(JSON)。

- `generate_report(...)` 汇总情绪分布、时间趋势、关键词、高赞评论等为一个
  JSON，经 `file_utils.save_report` 保存到 report.json。

---

## utils/ —— 工具层

### utils/cleaner.py
文本清洗。`clean_dataframe(df)` 生成 `text_clean` 列（去除 URL、@用户、
[表情]、话题标签、特殊字符等），并按最小长度 `MIN_LEN` 过滤掉过短的无价值文本，
返回清洗后的新 DataFrame 供情绪分析使用。

### utils/loader.py
数据加载。

- `load_comments(path, cfg)` / `load_danmaku(path, cfg)` 把评论/弹幕 JSON
  分别读成 DataFrame（内部含时间戳解析 `_parse_timestamp`）。
- `load_meta(path)` 从文件反查视频元信息(bv_id/uid/uname/title)，
  供命令行单独调试、task 中缺元信息时兜底使用。

### utils/file_utils.py
文件保存。`save_comments` / `save_danmu` / `save_report` / `save_word_freq` /
`save_results`（带情绪标注 + 摘要）。所有产物按
`{uname}/{title}/{bv_id}/{time_str}/` 目录结构落盘，函数接受统一的 `time_str`。

### utils/log_utils.py
统一日志。`get_logger()` / `setup_logging()` 配置终端 + 文件日志；
`log_event()` 写结构化运行事件(jsonl)，便于回溯。

---

## config/ —— 配置层

### config/config.py
全局配置：各类目录路径、情绪后端(`SENTIMENT_BACKEND="bert"`)、BERT 模型名、
预警阈值、话题聚类参数(`TOPIC_MIN_DOCS` 等)、趋势图参数、统计字段等。

### config/hf_setup.py
HuggingFace 国内网络设置。设置 `HF_ENDPOINT=hf-mirror.com` 国内镜像 +
离线优先，须在 import transformers 之前生效（相关逻辑亦内联在
`bert_analyzer.py`/`web.py` 顶部以确保时机）。

---

## 已移除的文件（历史记录）

以下文件属于早期"UP 主数据预测"设想或旧情绪后端，已删除，不在当前架构中：

- `features/`（含 `sentiment.py` 旧 SnowNLP 后端、`comment_analysis.py`
  高频评论统计）—— 情绪已统一用 BERT，高频评论统计已下线。
- `crawler/fetch_videos.py` —— UP 主视频列表采集（预测项目遗留）。
- `models/video.py` 及 `tests/test_model_video.py` —— 预测项目的数据结构与测试。
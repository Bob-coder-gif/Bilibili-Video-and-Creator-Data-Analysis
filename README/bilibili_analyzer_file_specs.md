# 文件职责说明

> 逐个说明每个 Python 文件的职责、关键函数与依赖关系，配合《项目架构文档》一起看。

---

## app/ —— Web 服务与任务调度

### app/web.py
Flask 网页后端，项目唯一入口（`python -m app.web`），同时内嵌前端页面（HTML/JS）。

- 第一行 `import config.hf_setup`，保证 HuggingFace 环境变量在任何模型库加载前生效。
- 启动时检查登录态，没有则先弹出浏览器完成登录，再启动服务。
- 页面：`/`（提交 BV 号 + 进度条 + 队列面板 + 历史列表）、`/video/<bv_id>`（详情页）。
- 接口：
  - `POST /api/analyze` 提交任务，立刻返回 task_id
  - `GET  /api/task/<task_id>` 轮询任务进度
  - `GET  /api/queue` 队列概览（正在跑 + 排队列表）
  - `POST /api/task/<task_id>/cancel` 取消排队中的任务
  - `POST /api/queue/clear` 清空队列（仅排队中的）
  - `GET  /api/history` 已分析视频列表
  - `GET  /api/history/<bv_id>` 某视频详情（历史 / 最新预警 / 最新话题）
  - `GET  /api/image/<bv_id>/<kind>` 图片（trend / wordcloud / density / top_danmu）
- 所有带 bv_id 的路由都校验 BV 号格式；前端插入标题、昵称、话题词前做 HTML 转义。
- 过滤 werkzeug 的逐条请求日志，终端只保留启动信息和业务日志。

### app/task_runner.py
任务队列：`queue.Queue` + 单个 worker 线程串行执行。

- `submit_task(bv_id)` 入队，返回 task_id
- `get_task(task_id)` 查进度（排队中时附带"前面还有几个"）
- `get_queue_overview()` 队列概览
- `cancel_task(task_id)` / `clear_queue()` 取消 / 清空排队任务（标记取消，worker 取到后跳过）
- worker 依次调用三个 pipeline，通过 progress 回调把进度写回内存任务表；
  失败时按异常类型给出不同提示（风控 / 视频不存在 / 未登录 / 其他）。
- 已结束的任务只保留最近 100 个。

---

## crawler/ —— 数据采集层

### crawler/bilibili_state.py
登录态管理 + 浏览器启动。

- `has_login_state()` 登录态文件是否存在。
- `save_login_state()` 弹出可见浏览器，手动登录后保存 Cookie。
- `launch_browser(p, headless=None)` 按 `config.BROWSER_ENGINE` 启动浏览器，失败时切换
  到备用引擎；`headless` 不传时使用 `config.HEADLESS`；chromium 使用新版无头模式。

### crawler/fetch_comments.py
爬取评论（含楼中楼回复）。

- `fetch_comments(bv_id, max_count, progress)`：打开视频页 → 滚动触发评论分页 →
  拦截浏览器的评论 API 响应收集主评论 → 统一请求每条主评论的第一页回复。
- 返回 `{rpid: {type, mid, text, like, name, timestamp, replies: [...]}}`。
- 打开页面时顺便读取 `window.__INITIAL_STATE__.videoData` 并缓存，供 `get_video_info` 使用。
- 健壮性：等待网络空闲 + 整页重试（解决连续任务偶发 0 条评论）；回复请求随机间隔，
  遇到风控立即停止；任务结束后随机等待几秒再开始下一个任务。
- 没有登录态时抛出 `BiliLoginRequiredError`。

### crawler/fetch_danmu.py
爬取弹幕。

- `fetch_danmu(bv_id)`：`get_cid(bv_id)` 取第 1 P 的 cid → 请求 `list.so` 弹幕 XML →
  `parse_danmu(xml)` 解析成 `[{time, type, size, color, timestamp, text}, ...]`。
- 请求走 `http_utils.bili_get`；失败时抛异常，不再静默返回空列表。

### crawler/get_info_from_browser.py
获取视频元信息与统计数据，三级获取并缓存 view 接口数据：
页面缓存 → 带 Cookie 的 API 请求 → 被风控时用浏览器兜底。

- `get_video_info(bv_id)` → `(video_info, stat)`，`video_info = [uid, uname, title]`，
  `stat` 为播放 / 弹幕 / 评论 / 收藏 / 投币 / 分享 / 点赞计数。
- `get_cid(bv_id)` → 第 1 P 的 cid。
- `cache_video_data(bv_id, video_data)` 供 fetch_comments 写入缓存（有效期 30 分钟）。

---

## analyzer/ —— 分析层

### analyzer/bert_analyzer.py
BERT 中文情绪分析。

- `analyze(df, cfg)`：对 `text_clean` 列推理，新增 `bert_score`（正向概率 0~1）和
  `bert_label`（正向 / 中性 / 负向，按 `POS_THRESHOLD / NEG_THRESHOLD` 划分）。
- 模型 `uer/roberta-base-finetuned-jd-binary-chinese`，模块级单例，每批 64 条。
- `local_files_only` 跟随 `config.HF_OFFLINE`；本地没有模型时给出明确的下载提示。

### analyzer/keyword_extractor.py
关键词与词频（jieba）。

- `extract_keywords(df, cfg, label_filter, label_col)` TF-IDF 关键词，可按情绪筛选。
- `word_frequency(df, cfg)` 分词词频。
- `load_stopwords(path)` 内置 B 站停用词 +（可选）自定义停用词文件，结果缓存；
  弹幕词云和话题聚类也复用这份停用词。

### analyzer/topic_analyzer.py
话题聚类（BERTopic）。

- `run_topic_analysis(texts, bv_id, video_info, labels, time_str)`：聚类并保存
  `topics.json`，每个话题包含关键词、规模、情绪分布、示例评论。
- 使用 jieba 分词的 CountVectorizer 提取中文话题词；`min_topic_size` 随评论数自适应。
- 评论数少于 `TOPIC_MIN_DOCS`、未安装 BERTopic 或执行出错时跳过并返回 None。

### analyzer/video_stats.py
视频统计数据。

- `save_video_stats(bv_id, video_info, stat, time_str)`：保存本次快照，追加到
  `history.json`，累计达到 `MIN_POINTS_FOR_TREND` 次后重绘趋势图。
- `get_history(bv_id, video_info)` 读取历史；`history_file(...)` 返回历史文件路径。
- 趋势图两个子图：播放 / 弹幕 / 评论，点赞 / 投币 / 收藏 / 分享。

### analyzer/warning_detector.py
舆情预警。

- `record_sentiment_summary(...)` 把本次情绪计数补写进历史的最新一条记录。
- `detect_warnings(history)` 三类预警：负向占比过高、负向占比骤升、播放量暴增。
- `save_warnings(...)` 保存 `warnings.json`。

---

## pipeline/ —— 流程编排层

三个阶段通过 `task` 字典依次传递，`progress` 为可选进度回调。

### pipeline/crawler_pipeline.py
采集阶段：生成 `time_str` → 爬评论 → 获取视频信息 → 爬弹幕 → 弹幕可视化。
返回包含 `bv_id / video_info / comments / danmus / comments_path / danmaku_path /
stat / time_str` 的 task。

### pipeline/sentiment_pipeline.py
情绪分析阶段：加载 → 清洗 → BERT → 保存标注结果 → 关键词 / 词频 → `report.json`。
向 task 写入 `report_path / label_col / comment_texts / comment_labels / sentiment_summary`。

### pipeline/pipeline_data_analysis.py
统计 / 预警 / 话题阶段：统计快照 + 趋势图 → 补写情绪计数 + 预警检测 → 话题聚类。
三步顺序不可调换（预警依赖先落盘的统计记录和情绪计数）。

---

## visualization/ —— 可视化层

### visualization/danmu_vis.py
弹幕三张图，保存到 `data/processed/danmu/.../{bv_id}/{time_str}/`：

- `plot_top_danmu(...)` 高频弹幕柱状图
- `plot_danmu_density(...)` 弹幕随视频进度的密度图（默认 30 秒一格）
- `plot_danmu_wordcloud(...)` 弹幕词云（去停用词；无有效词语时跳过）

### visualization/report.py
- `generate_report(...)` 汇总情绪分布、评论按日情绪趋势、弹幕情绪时间轴、正负向关键词、
  高赞评论为一个 JSON，经 `file_utils.save_report` 保存。

---

## utils/ —— 工具层

### utils/http_utils.py
B 站接口请求的唯一出口。

- `bili_get(url, ...)` 原始响应（弹幕 XML 用），`bili_get_json(url, ...)` 返回 `data` 字段。
- 自动带完整 UA 和登录 Cookie；HTTP 412 立即抛风控异常，网络错误和 5xx 指数退避重试。
- `parse_bili_body(body)` 统一校验业务码（浏览器内 fetch 的结果也用它）。
- 异常类：`BiliRequestError` 及其子类 `BiliRiskControlError / BiliNotFoundError /
  BiliLoginRequiredError`。

### utils/file_utils.py
- `safe_name(name)` 把 UP 主名 / 标题转成合法目录名。
- `video_dir(root, video_info, bv_id, time_str)` 拼接并创建产物目录，所有模块共用。
- `save_comments / save_danmu / save_report / save_word_freq / save_results`。

### utils/loader.py
- `load_comments(path, cfg)` 主评论和回复展开为一张表
  （列：id / text / time / like / user / source）。
- `load_danmaku(path, cfg)` 弹幕表（列：id / text / video_time(秒) / source）。

### utils/cleaner.py
`clean_dataframe(df)` 生成 `text_clean` 列（去 URL、@用户、[表情]、话题标签、
特殊字符等），过滤掉长度小于 `MIN_LEN` 的文本。

### utils/plot_utils.py
设置 matplotlib 的 Agg 后端（后台线程画图必需），自动查找系统中文字体，
提供 `CJK_FONT_PATH` 给词云使用。

### utils/log_utils.py
- `get_logger()` / `setup_logging(verbose)`：终端默认 INFO，文件 `logs/debug/` 全量 DEBUG；
  屏蔽 jieba / transformers / huggingface_hub 的终端噪音。
- `log_event(event, **fields)`：写结构化事件到 `logs/runtime/{date}.jsonl`（线程安全）。

---

## config/ —— 配置层

### config/config.py
全局配置：数据目录、JSON 字段映射、BERT 模型与情绪阈值、关键词数量、趋势图参数、
浏览器引擎与无头模式、预警阈值、话题聚类参数、`HF_OFFLINE` 开关。

### config/hf_setup.py
设置 `HF_ENDPOINT=https://hf-mirror.com`，并按 `HF_OFFLINE` 设置离线模式。
必须在 import transformers / bertopic 之前被 import（web.py、bert_analyzer.py、
topic_analyzer.py 都在最前面 import 它）。

---

## 已移除的文件（历史记录）

- `features/`（旧 SnowNLP 情绪后端、高频评论统计）—— 情绪统一用 BERT。
- `crawler/fetch_videos.py`、`models/video.py`、`tests/test_model_video.py` ——
  早期"UP 主数据预测"设想的遗留。
- `app/main.py` —— 命令行入口，已由网页入口取代。
- `debug_info.py` —— 排查 HTTP 412 时的一次性诊断脚本，问题修复后删除。

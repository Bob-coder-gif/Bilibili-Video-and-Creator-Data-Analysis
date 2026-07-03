"""
全局配置文件
根据实际情况修改以下配置
"""

# ============================================================
# 输入文件配置
# ============================================================

# COMMENTS_FILE = "data/raw/profile/temp_profile.json" # 临时默认值，实际运行时会被 --comments 参数覆盖
# DANMAKU_FILE = "data/raw/profile/temp_danmaku.json"


#-------------------------------------------
# temp 修bug
COMMENTS_FILE = ""
DANMAKU_FILE = ""

COMMENTS_DIR= "data/raw/comments"
DANMAKU_DIR = "data/raw/danmu"

#------------------------------------------

# JSON 字段映射 —— 必须根据你的 JSON 结构修改
COMMENT_TEXT_FIELD = "text" 
COMMENT_ID_FIELD = "mid"    
COMMENT_TIME_FIELD = "timestamp" 
COMMENT_USER_FIELD = "name"   # 对应 uname
COMMENT_LIKE_FIELD = "like"   # 点赞数字段

# 弹幕结构: [ { "time": 120.8, "text": "内容" } ]
DANMAKU_TEXT_FIELD = "text"
DANMAKU_TIME_FIELD = "time" 
DANMAKU_ID_FIELD = "timestamp" 


# ============================================================
# 情绪分析配置
# ============================================================

# 分析后端: "bert" 
#   bert    : 调用 Hugging Face 模型, 效果好, 首次需下载

SENTIMENT_BACKEND = "bert"

# 使用 bert 时的模型名（需要能访问 HuggingFace 或本地路径）
BERT_MODEL_NAME = "uer/roberta-base-finetuned-jd-binary-chinese"

# 情绪分类阈值（仅 snownlp）
POS_THRESHOLD = 0.6   # >= 正向
NEG_THRESHOLD = 0.4   # <= 负向
# 中间区间视为中性

# ============================================================
# 输出配置
# ============================================================
OUTPUT_DIR = "data/report"  # 报告根目录
# 最终报告实际路径由 file_utils.save_report 自动拼接为:
#   data/report/{uname}/{title}/{bv_id}_{time_str}_report.json
SAVE_ANNOTATED_JSON = True   # 是否保存带情绪标签的完整 JSON
REPORT_SUFFIX = "report.json"  # 报告文件名后缀（拼接在 bv_id_时间 之后）

OUTPUT_FILE = ""

# ============================================================
# 关键词 / 话题配置（用于热词分析）
# ============================================================
STOPWORDS_FILE = ""    # 自定义停用词文件路径，留空则用内置
TOPN_KEYWORDS  = 50    # 提取 Top-N 关键词

# ============================================================
# 视频统计数据 / 趋势分析配置（新增，仅追加，未改动以上任何内容）
# ============================================================

# B 站 stat 接口原生字段 -> 中文显示名（用于画图 legend / 标题）
# 对应 https://api.bilibili.com/x/web-interface/view 返回的 data.stat
VIDEO_STAT_FIELDS = {
    "view":     "播放量",
    "danmaku":  "弹幕数",
    "reply":    "评论数",
    "favorite": "收藏数",
    "coin":     "投币数",
    "share":    "分享数",
    "like":     "点赞数",
}

# 趋势图中重点画的"三连"指标（点赞/投币/收藏）
SANLIAN_FIELDS = ["like", "coin", "favorite"]

# 视频统计数据保存根目录
# 实际路径由 analyzer/video_stats.py 自动拼接为:
#   data/analysis/{uname}/{title}/{bv_id}_{time_str}_stats_analysis.json
#   data/analysis/{uname}/{title}/{bv_id}_history.json
#   data/analysis/{uname}/{title}/{bv_id}_trend.png
ANALYSIS_DIR = "data/analysis"

# 历史记录文件名后缀（保存在每个 bv_id 自己的目录下，文件名为 {bv_id}_{HISTORY_FILENAME_SUFFIX}）
HISTORY_FILENAME_SUFFIX = "history.json"

# 至少累计多少条历史记录才开始画趋势图
MIN_POINTS_FOR_TREND = 2

# 趋势图 DPI / 尺寸
TREND_FIG_DPI = 150
TREND_FIG_SIZE = (10, 6)

# ============================================================
# Pipeline 间数据传递（"黑板"变量，新增）
# ============================================================
# crawler_pipeline() 拿到 bv_id / video_info 后写入这里，
# get_video_info() 顺手把同一次请求里的 stat 也写入这里，
# 后续的 pipeline_data_analysis() 等其他 pipeline 直接从这里读取，
# 不需要再额外传参或重新请求。

CURRENT_BV_ID = ""          # 当前处理的视频 BV 号
CURRENT_VIDEO_INFO = []     # [UID, uname, title]
CURRENT_VIDEO_STAT = {}     # B 站原生 stat 字段: view/danmaku/reply/favorite/coin/share/like 等


# ============================================================
# 浏览器自动化配置（新增，仅追加）
# ============================================================
# 原来 fetch_comments.py 和 bilibili_state.py 各自硬编码了一份
# STORAGE_PATH 和浏览器启动逻辑，现在统一从这里读取，改一处即可。

# 登录态保存路径
STORAGE_PATH = "./bilibili_data/bilibili_state.json"

# 主用浏览器引擎: "chromium" | "firefox" | "webkit"
BROWSER_ENGINE = "chromium"

# 主用引擎启动失败时自动尝试的备用引擎，设为 None 则不自动切换
BROWSER_FALLBACK_ENGINE = "firefox"

# 是否无头模式（True=不弹窗口，适合服务器跑；登录/调试建议 False）
HEADLESS = False

# 把以下配置项追加到 config/__init__.py 末尾（不要改动已有内容）

# ============================================================
# 舆情预警配置（需求 3）
# ============================================================
WARNING_NEG_RATIO_THRESHOLD = 0.4   # 负向占比 >= 此值触发预警（0.4 = 40%）
WARNING_NEG_RATIO_JUMP = 0.15       # 负向占比比上次高出 >= 此值触发"骤升"预警
WARNING_VIEW_SPIKE_RATIO = 2.0      # 播放量 >= 上次的此倍数触发"暴增"预警

# ============================================================
# 话题聚类配置（需求 1，BERTopic）
# ============================================================
TOPIC_DIR = "data/topic"            # 话题结果保存根目录
TOPIC_MIN_DOCS = 20                 # 评论数少于此值跳过聚类（数据太少聚不出话题）
TOPIC_NR = "auto"                   # 话题数: "auto" 自动合并，或填整数固定话题数

# ============================================================
# HuggingFace 网络环境配置（国内适配）
# ============================================================
# 解决国内不挂梯子无法访问 huggingface.co 的问题。
# 具体的环境变量设置在 config/hf_setup.py 里，本开关只控制"是否优先离线"。
#
#   HF_OFFLINE = True  （默认，推荐）：
#       优先使用本地已下载的模型缓存，命中缓存时完全不联网、秒加载。
#       适合"模型之前已经下过"的情况（你就是这种）。
#       注意：若本地没有该模型缓存，会直接报错（不会自动去下载）。
#
#   HF_OFFLINE = False：
#       允许联网，并通过国内镜像 hf-mirror.com 下载模型（不需要梯子）。
#       使用场景：第一次下载模型、换了新模型、或本地缓存损坏时，
#       临时改成 False 跑一次把模型下下来，下载完成后再改回 True。
HF_OFFLINE = True
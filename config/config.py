"""
config/config.py
全局配置文件，根据实际情况修改以下配置。

2026-09-28 清理：
    删除已无引用的配置：COMMENTS_FILE / DANMAKU_FILE / OUTPUT_FILE / REPORT_SUFFIX /
    SENTIMENT_BACKEND / CURRENT_BV_ID / CURRENT_VIDEO_INFO / CURRENT_VIDEO_STAT
    （"黑板"全局变量已被 task 字典取代，命令行入口已删除）。
    POS_THRESHOLD / NEG_THRESHOLD 改为 BERT 的中性区间阈值（原来只给 SnowNLP 用）。
    新增 PROCESSED_DANMU_DIR，统一弹幕图片目录（原来在两个文件里各写死一份）。
    HEADLESS 默认改为 True，并且现在真正生效（原来调用方写死了 headless=True）。
"""

# ============================================================
# 数据目录
# ============================================================
# 所有产物按 {根目录}/{uname}/{title}/{bv_id}/{time_str}/ 保存，
# uname / title 会先经过 utils.file_utils.safe_name 去掉文件名非法字符。
COMMENTS_DIR = "data/raw/comments"            # 原始评论
DANMAKU_DIR = "data/raw/danmu"                # 原始弹幕
OUTPUT_DIR = "data/report"                    # 情绪报告 / 标注结果 / 词频
ANALYSIS_DIR = "data/analysis"                # 统计快照 / 历史 / 趋势图 / 预警
TOPIC_DIR = "data/topic"                      # 话题聚类结果
PROCESSED_DANMU_DIR = "data/processed/danmu"  # 弹幕可视化图片

# ============================================================
# JSON 字段映射（与 crawler 保存的原始数据结构对应）
# ============================================================
# 评论结构: {"comments": {rpid: {"text", "like", "name", "timestamp", "replies": [...]}}}
COMMENT_TEXT_FIELD = "text"
COMMENT_TIME_FIELD = "timestamp"   # 评论发布时间（Unix 秒）
COMMENT_USER_FIELD = "name"
COMMENT_LIKE_FIELD = "like"

# 弹幕结构: {"danmus": [{"time": 120.8, "text": "内容", "timestamp": 17771...}]}
DANMAKU_TEXT_FIELD = "text"
DANMAKU_TIME_FIELD = "time"        # 弹幕在视频中出现的时间（秒，float）
DANMAKU_ID_FIELD = "timestamp"

# ============================================================
# 情绪分析（BERT）
# ============================================================
BERT_MODEL_NAME = "uer/roberta-base-finetuned-jd-binary-chinese"

# 该模型是二分类（正/负），没有"中性"输出。
# 这里用"正向概率"划分三类：>= POS_THRESHOLD 为正向，<= NEG_THRESHOLD 为负向，
# 中间区间视为中性（模型拿不准的文本）。
POS_THRESHOLD = 0.6
NEG_THRESHOLD = 0.4

SAVE_ANNOTATED_JSON = True   # 是否保存带情绪标签的完整 JSON

# ============================================================
# 关键词
# ============================================================
STOPWORDS_FILE = ""    # 自定义停用词文件路径（每行一个词），留空则只用内置停用词
TOPN_KEYWORDS = 50     # 提取 Top-N 关键词

# ============================================================
# 视频统计数据 / 趋势图
# ============================================================
# B 站 view 接口 data.stat 字段 -> 中文显示名
VIDEO_STAT_FIELDS = {
    "view":     "播放量",
    "danmaku":  "弹幕数",
    "reply":    "评论数",
    "favorite": "收藏数",
    "coin":     "投币数",
    "share":    "分享数",
    "like":     "点赞数",
}

SANLIAN_FIELDS = ["like", "coin", "favorite"]   # 趋势图下半部分画的"三连"指标

HISTORY_FILENAME_SUFFIX = "history.json"   # 保存在 data/analysis/{uname}/{title}/{bv_id}/ 下
MIN_POINTS_FOR_TREND = 2                   # 至少累计多少次抓取才画趋势图
TREND_FIG_DPI = 150
TREND_FIG_SIZE = (10, 6)

# ============================================================
# 浏览器自动化
# ============================================================
STORAGE_PATH = "./bilibili_data/bilibili_state.json"   # 登录态（Cookie）保存路径

BROWSER_ENGINE = "chromium"            # "chromium" | "firefox" | "webkit"
BROWSER_FALLBACK_ENGINE = "firefox"    # 主引擎启动失败时的备用引擎，None 表示不切换

# 爬取时是否无头（不弹窗口）。调试爬虫时可改成 False 观察页面。
# 首次登录不受此项影响，始终弹出可见窗口。
HEADLESS = True

# ============================================================
# 舆情预警
# ============================================================
WARNING_NEG_RATIO_THRESHOLD = 0.4   # 负向占比 >= 此值触发预警
WARNING_NEG_RATIO_JUMP = 0.15       # 负向占比比上次高出 >= 此值触发"骤升"预警
WARNING_VIEW_SPIKE_RATIO = 2.0      # 播放量 >= 上次的此倍数触发"暴增"预警

# ============================================================
# 话题聚类（BERTopic）
# ============================================================
TOPIC_MIN_DOCS = 20     # 评论数少于此值跳过聚类
TOPIC_NR = "auto"       # 话题数: "auto" 自动合并，或填整数固定话题数

# ============================================================
# HuggingFace（国内网络）
# ============================================================
# 具体环境变量设置见 config/hf_setup.py。
#   True （默认）：只用本地已下载的模型缓存，不联网。本地没有缓存会报错。
#   False        ：允许联网，通过国内镜像 hf-mirror.com 下载模型。
# 第一次使用（BERT 情绪模型、BERTopic 的向量模型都还没下载）时改成 False
# 跑一次任务，下载完成后改回 True。
HF_OFFLINE = True
#HF_OFFLINE = False

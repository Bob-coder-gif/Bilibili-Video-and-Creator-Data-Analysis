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

# 分析后端: "snownlp" | "bert" | "both"
#   snownlp : 纯本地, 速度快, 中文效果一般
#   bert    : 调用 Hugging Face 模型, 效果好, 首次需下载
#   both    : 两者都跑, 结果对比
SENTIMENT_BACKEND = "snownlp"

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
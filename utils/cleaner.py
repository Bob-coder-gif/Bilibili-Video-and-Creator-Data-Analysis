"""
utils/cleaner.py
文本清洗：去除 URL、表情符号、特殊字符等
"""

import re
from utils.log_utils import get_logger

logger = get_logger()


# B 站常见无意义短弹幕（可自行扩充）
_NOISE_PATTERNS = [
    r"https?://\S+",          # URL
    r"www\.\S+",
    r"@\S+",                  # @用户
    r"\[.*?\]",               # [表情]
    r"【.*?】",
    r"#\S+",                  # 话题标签
    r"\d{4}-\d{2}-\d{2}",    # 日期
    r"[^\u4e00-\u9fffA-Za-z0-9，。！？、；：\u201c\u201d\u2018\u2019（）【】《》\s]",
]
_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS))

# 过短文本过滤阈值（字符数）
MIN_LEN = 2


def clean_text(text: str) -> str:
    """清洗单条文本，返回干净字符串"""
    text = str(text).strip()
    text = _NOISE_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_valid(text: str) -> bool:
    """判断清洗后文本是否有分析价值"""
    return len(text) >= MIN_LEN


def clean_dataframe(df, text_col: str = "text"):
    """对整个 DataFrame 做清洗，返回新 DataFrame"""
    df = df.copy()
    df["text_clean"] = df[text_col].map(clean_text)
    df = df[df["text_clean"].map(is_valid)].reset_index(drop=True)
    # 清洗前后的数量是排查"为什么数据变少了"的关键信息，但属于过程细节
    logger.debug(f"[cleaner] 清洗后保留 {len(df)} 条")
    return df
"""
analyzer/snownlp_analyzer.py
基于 SnowNLP 的轻量情绪分析（无需 GPU，适合快速运行）
情绪得分 0~1，越高越正向
"""

import pandas as pd
from tqdm import tqdm

try:
    from snownlp import SnowNLP
except ImportError:
    raise ImportError("请先安装: pip install snownlp")


def _score(text: str) -> float:
    """对单条文本打分，出错时返回 0.5（中性）"""
    try:
        return SnowNLP(text).sentiments
    except Exception:
        return 0.5


def _label(score: float, pos_thr: float, neg_thr: float) -> str:
    if score >= pos_thr:
        return "正向"
    if score <= neg_thr:
        return "负向"
    return "中性"


def analyze(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """
    输入带 text_clean 列的 DataFrame
    返回新增 snownlp_score / snownlp_label 两列的 DataFrame
    """
    df = df.copy()
    print("[SnowNLP] 开始打分...")
    scores = []
    for text in tqdm(df["text_clean"], desc="SnowNLP"):
        scores.append(_score(text))

    df["snownlp_score"] = scores
    df["snownlp_label"] = df["snownlp_score"].map(
        lambda s: _label(s, cfg.POS_THRESHOLD, cfg.NEG_THRESHOLD)
    )
    print("[SnowNLP] 完成")
    return df

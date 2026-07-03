"""
analyzer/keyword_extractor.py
基于 jieba TF-IDF 提取高频关键词 / 话题词
"""

import os
import collections
import pandas as pd

try:
    import jieba
    import jieba.analyse
except ImportError:
    raise ImportError("请先安装: pip install jieba")


# 内置停用词（B 站场景常见无意义词）
_BUILTIN_STOPWORDS = {
    "的", "了", "是", "我", "你", "他", "她", "它", "们",
    "这", "那", "就", "都", "说", "没", "也", "不", "有",
    "在", "和", "啊", "吧", "哦", "嗯", "哈", "哈哈", "哈哈哈",
    "666", "233", "2333", "笑", "太", "真的", "感觉",
    "一个", "一下", "什么", "怎么", "为什么", "因为", "所以",
    "但是", "还是", "只是", "可以", "可能", "应该", "视频",
    "up", "up主", "主", "弹幕", "评论", "bilibili", "b站",
}


def _load_stopwords(path: str) -> set:
    words = set(_BUILTIN_STOPWORDS)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            words.update(line.strip() for line in f if line.strip())
    return words


def extract_keywords(
    df: pd.DataFrame,
    cfg,
    label_filter: str | None = None,
    label_col: str | None = None,
) -> list[dict]:
    """
    从 text_clean 列提取关键词
    label_filter: None=全部, '正向'/'负向'/'中性' = 按情绪过滤
    label_col: 用哪一列做情绪过滤（如 "bert_label" / "snownlp_label"）。
               不传时按旧逻辑依次尝试 "label" -> "snownlp_label" -> 全空兜底，
               保持对旧调用方式的兼容。
    返回 [{"word": str, "weight": float}, ...]
    """
    stopwords = _load_stopwords(cfg.STOPWORDS_FILE)
    jieba.analyse.set_stop_words(cfg.STOPWORDS_FILE) if cfg.STOPWORDS_FILE else None

    if label_filter is None:
        sub = df
    else:
        if label_col and label_col in df.columns:
            col = df[label_col]
        else:
            # 未显式指定 label_col 时，沿用旧的猜测逻辑作为兜底
            col = df.get("label", df.get("snownlp_label", pd.Series(index=df.index, dtype=object)))
        sub = df[col == label_filter]

    corpus = " ".join(sub["text_clean"].dropna().tolist())

    if not corpus.strip():
        return []

    keywords = jieba.analyse.extract_tags(
        corpus,
        topK=cfg.TOPN_KEYWORDS,
        withWeight=True,
        allowPOS=("ns", "n", "vn", "v", "an", "nz", "eng"),
    )
    return [
        {"word": w, "weight": round(float(wt), 4)}
        for w, wt in keywords
        if w not in stopwords and len(w) > 1
    ]


def word_frequency(df: pd.DataFrame, cfg) -> list[dict]:
    """简单词频统计（jieba 分词），补充 TF-IDF 之外的视角"""
    stopwords = _load_stopwords(cfg.STOPWORDS_FILE)
    counter: collections.Counter = collections.Counter()
    for text in df["text_clean"].dropna():
        words = jieba.cut(text)
        for w in words:
            w = w.strip()
            if len(w) > 1 and w not in stopwords:
                counter[w] += 1
    return [{"word": w, "count": c} for w, c in counter.most_common(cfg.TOPN_KEYWORDS)]
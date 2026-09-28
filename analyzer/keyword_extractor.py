"""
analyzer/keyword_extractor.py
基于 jieba 的关键词（TF-IDF）与词频提取

修改时间：
    2026-09-28
----------------------------------
    1. _load_stopwords 改为公开的 load_stopwords，弹幕词云和话题聚类也复用同一份停用词。
    2. extract_keywords 的 label_col 改为按情绪过滤时必传，删除旧的列名猜测逻辑
       （"label" / "snownlp_label" 都已不存在）。
    3. 停用词文件只在第一次调用时加载一次（原来每次调用都重新读文件、重新设置 jieba）。
    4. 内置停用词补充常见虚词和代词（"就是""这些""没有"等），它们在词云里占位置但没有信息量。
"""

import collections
import os
from functools import lru_cache

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
    # 常见虚词 / 代词 / 连词（2026-09-28 补充）
    "就是", "没有", "这些", "那些", "这个", "那个", "这样", "那样", "这么", "那么",
    "这帮", "那帮", "于是", "然后", "如果", "虽然", "而且", "或者", "已经", "还有",
    "不是", "我们", "你们", "他们", "她们", "自己", "大家", "一样", "知道", "觉得",
    "现在", "时候", "真是", "确实", "好像", "其实", "一直", "一定", "一手", "一眼",
    "还要", "只有", "为了", "出来", "起来", "一些", "有点", "这种", "那种", "东西",
}

_POS_ALLOW = ("ns", "n", "vn", "v", "an", "nz", "eng")


@lru_cache(maxsize=None)
def load_stopwords(path: str = "") -> frozenset:
    """内置停用词 + 可选的自定义停用词文件（每行一个词）"""
    words = set(_BUILTIN_STOPWORDS)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            words.update(line.strip() for line in f if line.strip())
        jieba.analyse.set_stop_words(path)
    return frozenset(words)


def extract_keywords(
    df: pd.DataFrame,
    cfg,
    label_filter: str | None = None,
    label_col: str | None = None,
) -> list[dict]:
    """
    从 text_clean 列用 TF-IDF 提取关键词。
    label_filter: None=全部；"正向" / "负向" / "中性" = 只取该情绪的文本（需同时传 label_col）
    返回 [{"word": str, "weight": float}, ...]
    """
    stopwords = load_stopwords(cfg.STOPWORDS_FILE)

    if label_filter is None:
        sub = df
    elif label_col and label_col in df.columns:
        sub = df[df[label_col] == label_filter]
    else:
        return []

    corpus = " ".join(sub["text_clean"].dropna().tolist())
    if not corpus.strip():
        return []

    keywords = jieba.analyse.extract_tags(
        corpus, topK=cfg.TOPN_KEYWORDS, withWeight=True, allowPOS=_POS_ALLOW,
    )
    return [
        {"word": w, "weight": round(float(wt), 4)}
        for w, wt in keywords
        if w not in stopwords and len(w) > 1
    ]


def word_frequency(df: pd.DataFrame, cfg) -> list[dict]:
    """简单词频统计（jieba 分词），补充 TF-IDF 之外的视角"""
    stopwords = load_stopwords(cfg.STOPWORDS_FILE)
    counter = collections.Counter()
    for text in df["text_clean"].dropna():
        for w in jieba.cut(text):
            w = w.strip()
            if len(w) > 1 and w not in stopwords:
                counter[w] += 1
    return [{"word": w, "count": c} for w, c in counter.most_common(cfg.TOPN_KEYWORDS)]
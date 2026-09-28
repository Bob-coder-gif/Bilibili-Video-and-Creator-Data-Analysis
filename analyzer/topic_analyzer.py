"""
analyzer/topic_analyzer.py
话题聚类分析 —— 基于 BERTopic

结果路径: data/topic/{uname}/{title}/{bv_id}/{time_str}/topics.json
数据不足 / 未安装 BERTopic / 聚类出错时返回 None，不影响主流程。

修改时间：
    2026-09-28
----------------------------------
    1. 修复中文话题关键词是整句话的问题：BERTopic 默认的 CountVectorizer 按空格和
       标点切词，中文没有空格，一整条评论会被当成一个"词"。现在改用 jieba 分词，
       并去掉停用词。
    2. min_topic_size 随评论数自适应（默认值 10 在几十条评论时几乎全部被判为离群点，
       经常聚出 0 个话题）。
    3. 目录拼接改用 utils.file_utils.video_dir（统一处理标题里的非法字符）。
    4. 首次使用需要下载向量模型（受 config.HF_OFFLINE 控制），失败时日志里给出提示。
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

import config.hf_setup  # noqa: F401  必须在 import bertopic 之前
import config.config as cfg
from utils.file_utils import video_dir
from utils.log_utils import get_logger, log_event

logger = get_logger()


def _bertopic_available() -> bool:
    try:
        import bertopic  # noqa: F401
        return True
    except ImportError:
        return False


def _build_vectorizer():
    """jieba 分词 + 停用词的 CountVectorizer，给 BERTopic 提取话题关键词用"""
    import jieba
    from sklearn.feature_extraction.text import CountVectorizer
    from analyzer.keyword_extractor import load_stopwords

    stopwords = load_stopwords(cfg.STOPWORDS_FILE)

    def tokenize(text):
        return [w for w in jieba.lcut(text) if len(w.strip()) > 1 and w not in stopwords]

    # token_pattern=None：显式声明不用默认正则，避免 sklearn 警告
    return CountVectorizer(tokenizer=tokenize, token_pattern=None, lowercase=False)


def analyze_topics(texts: list[str], labels: list[str] | None = None) -> dict | None:
    valid = [(i, t) for i, t in enumerate(texts) if t and str(t).strip()]
    if labels is not None and len(labels) != len(texts):
        logger.warning("[topic] labels 长度与 texts 不一致，忽略情绪标签")
        labels = None

    doc_count = len(valid)
    if doc_count < cfg.TOPIC_MIN_DOCS:
        logger.info(f"ℹ️  评论数 {doc_count} 少于话题聚类所需的最小值 {cfg.TOPIC_MIN_DOCS}，跳过话题聚类")
        log_event("topic_skipped_too_few_docs", doc_count=doc_count, min_required=cfg.TOPIC_MIN_DOCS)
        return None

    if not _bertopic_available():
        logger.warning("[topic] 未安装 BERTopic，跳过话题聚类。安装命令: pip install bertopic")
        log_event("topic_skipped_no_bertopic")
        return None

    from bertopic import BERTopic
    docs = [t for _, t in valid]
    doc_labels = [labels[i] for i, _ in valid] if labels is not None else None

    logger.info(f"[topic] 开始话题聚类，共 {doc_count} 条文本")
    min_topic_size = max(3, min(10, doc_count // 20))

    try:
        topic_model = BERTopic(
            language="multilingual",
            nr_topics=cfg.TOPIC_NR,
            min_topic_size=min_topic_size,
            vectorizer_model=_build_vectorizer(),
            verbose=False,
        )
        topic_ids, _ = topic_model.fit_transform(docs)
    except Exception as e:
        hint = ""
        if getattr(cfg, "HF_OFFLINE", True):
            hint = "（如果是首次使用，可能是本地没有向量模型缓存：把 config.HF_OFFLINE 改为 False 跑一次下载）"
        logger.warning(f"[topic] 话题聚类执行失败，跳过: {type(e).__name__}: {e}{hint}")
        log_event("topic_failed", error=f"{type(e).__name__}: {e}")
        return None

    topics_out = []
    for _, row in topic_model.get_topic_info().iterrows():
        tid = int(row["Topic"])
        if tid == -1:   # -1 是 BERTopic 的离群点
            continue
        keywords = [w for w, _ in (topic_model.get_topic(tid) or [])[:10]]
        member_idx = [i for i, t in enumerate(topic_ids) if t == tid]
        sentiment = None
        if doc_labels is not None:
            sentiment = dict(Counter(doc_labels[i] for i in member_idx))
        topics_out.append({
            "topic_id": tid,
            "keywords": keywords,
            "size": len(member_idx),
            "sentiment": sentiment,
            "examples": [docs[i] for i in member_idx[:3]],
        })

    topics_out.sort(key=lambda t: t["size"], reverse=True)
    logger.info(f"[topic] 话题聚类完成，共聚出 {len(topics_out)} 个话题")
    log_event("topic_done", doc_count=doc_count, topic_count=len(topics_out))
    return {
        "backend": "bertopic",
        "doc_count": doc_count,
        "topic_count": len(topics_out),
        "topics": topics_out,
    }


def save_topics(result: dict, bv_id: str, video_info: list, time_str: str | None = None) -> str:
    """话题结果落盘到 data/topic/{uname}/{title}/{bv_id}/{time_str}/topics.json"""
    now = datetime.now()
    time_str = time_str or now.strftime("%Y%m%d_%H%M%S")
    path = video_dir(cfg.TOPIC_DIR, video_info, bv_id, time_str) / "topics.json"

    payload = {
        "bv_id": bv_id, "uname": video_info[1], "title": video_info[2],
        "analyze_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        **result,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"[topic] 话题结果已保存: {path}")
    log_event("topics_saved", bv_id=bv_id, path=str(path), topic_count=result.get("topic_count", 0))
    return str(path)


def run_topic_analysis(texts: list[str], bv_id: str, video_info: list,
                       labels: list[str] | None = None, time_str: str | None = None) -> dict | None:
    result = analyze_topics(texts, labels=labels)
    if result is None:
        return None
    result["topics_path"] = save_topics(result, bv_id, video_info, time_str=time_str)
    return result

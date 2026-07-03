"""
analyzer/topic_analyzer.py
话题聚类分析 —— 基于 BERTopic

修改时间：
    2026-06-27
-----------------------------
路径结构调整：
    话题结果带时间目录: data/topic/{uname}/{title}/{bv_id}/{time_str}/topics.json
    save_topics / run_topic_analysis 新增可选参数 time_str。

（BERTopic 为可选依赖、需要足够数据量等前提见下方各函数说明，未变）
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import config.config as cfg
from utils.log_utils import get_logger, log_event

logger = get_logger()


def _bertopic_available() -> bool:
    try:
        import bertopic  # noqa: F401
        return True
    except ImportError:
        return False


def _topic_dir(uname: str, title: str, bv_id: str, time_str: str) -> Path:
    d = Path(cfg.TOPIC_DIR) / uname / title / bv_id / time_str
    d.mkdir(parents=True, exist_ok=True)
    return d


def analyze_topics(texts: list[str], labels: list[str] | None = None) -> dict | None:
    valid = [(i, t) for i, t in enumerate(texts) if t and str(t).strip()]
    if labels is not None and len(labels) != len(texts):
        logger.warning("[topic] labels 长度与 texts 不一致，忽略情绪标签")
        labels = None

    doc_count = len(valid)
    if doc_count < cfg.TOPIC_MIN_DOCS:
        logger.info(
            f"ℹ️  评论数 {doc_count} 少于话题聚类所需的最小值 {cfg.TOPIC_MIN_DOCS}，"
            f"跳过话题聚类（数据更多时会自动启用）"
        )
        log_event("topic_skipped_too_few_docs", doc_count=doc_count, min_required=cfg.TOPIC_MIN_DOCS)
        return None

    if not _bertopic_available():
        logger.warning("[topic] 未安装 BERTopic，跳过话题聚类。安装命令: pip install bertopic")
        log_event("topic_skipped_no_bertopic")
        return None

    from bertopic import BERTopic
    docs = [t for _, t in valid]
    doc_labels = [labels[i] for i, _ in valid] if labels is not None else None

    logger.info(f"[topic] 开始话题聚类，共 {doc_count} 条文本（首次会下载模型，请耐心等待）")
    nr_topics = cfg.TOPIC_NR if cfg.TOPIC_NR != "auto" else "auto"

    try:
        topic_model = BERTopic(language="multilingual", nr_topics=nr_topics, verbose=False)
        topic_ids, _ = topic_model.fit_transform(docs)
    except Exception as e:
        logger.warning(f"[topic] 话题聚类执行失败，跳过: {type(e).__name__}: {e}")
        log_event("topic_failed", error=f"{type(e).__name__}: {e}")
        return None

    info = topic_model.get_topic_info()
    topics_out = []
    for _, row in info.iterrows():
        tid = int(row["Topic"])
        if tid == -1:
            continue
        kw_pairs = topic_model.get_topic(tid) or []
        keywords = [w for w, _ in kw_pairs[:10]]
        member_idx = [i for i, t in enumerate(topic_ids) if t == tid]
        size = len(member_idx)
        sentiment = None
        if doc_labels is not None:
            cnt = Counter(doc_labels[i] for i in member_idx)
            sentiment = {k: int(v) for k, v in cnt.items()}
        examples = [docs[i] for i in member_idx[:3]]
        topics_out.append({
            "topic_id": tid, "keywords": keywords, "size": size,
            "sentiment": sentiment, "examples": examples,
        })

    topics_out.sort(key=lambda t: t["size"], reverse=True)
    result = {
        "backend": "bertopic", "doc_count": doc_count,
        "topic_count": len(topics_out), "topics": topics_out,
    }
    logger.info(f"[topic] 话题聚类完成，共聚出 {len(topics_out)} 个话题")
    log_event("topic_done", doc_count=doc_count, topic_count=len(topics_out))
    return result


def save_topics(result: dict, bv_id: str, video_info: list, time_str: str | None = None) -> str:
    """
    话题结果落盘到 data/topic/{uname}/{title}/{bv_id}/{time_str}/topics.json
    time_str 不传则内部生成。
    """
    uname, title = video_info[1], video_info[2]
    now = datetime.now()
    time_str = time_str or now.strftime("%Y%m%d_%H%M%S")

    save_dir = _topic_dir(uname, title, bv_id, time_str)
    path = save_dir / "topics.json"

    payload = {
        "bv_id": bv_id, "uname": uname, "title": title,
        "analyze_time": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    payload.update(result)
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
    path = save_topics(result, bv_id, video_info, time_str=time_str)
    result["topics_path"] = path
    return result
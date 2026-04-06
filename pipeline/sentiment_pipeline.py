"""
sentiment_pipeline.py

功能：
    单视频评论 → 情绪分析 → 统计结果

使用技术：
    - Pipeline设计模式
    - 数据清洗
    - 加权统计（点赞）

修改时间：
    2026-04-06
"""

from crawler.fetch_comments import fetch_comments
from features.sentiment import get_sentiment_score


def run_sentiment_pipeline(bv_id):
    """
    主流程
    """

    comments = fetch_comments(bv_id)

    scores = []

    for c in comments:
        text = c["text"]
        like = c["like"]

        if len(text) < 2:
            continue

        try:
            score = get_sentiment_score(text)

            # ⭐ 点赞加权（核心亮点）
            weighted = score * (1 + like * 0.01)

            scores.append(weighted)

        except:
            continue

    if not scores:
        return None

    avg = sum(scores) / len(scores)

    return {
        "avg_score": avg,
        "positive": len([s for s in scores if s > 0.6]),
        "negative": len([s for s in scores if s < 0.4]),
        "neutral": len(scores) - len([s for s in scores if s > 0.6]) - len([s for s in scores if s < 0.4]),
        "total": len(scores)
    }
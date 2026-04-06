"""
sentiment.py

功能：
    文本情绪分析

使用技术：
    - SnowNLP（中文情绪分析）
    - 可扩展：BERT / Transformer

修改时间：
    2026-04-06
"""

from snownlp import SnowNLP


def get_sentiment_score(text):
    """
    输出：
        0~1 情绪值

    技术：
        - 朴素贝叶斯情感分析
    """
    return SnowNLP(text).sentiments
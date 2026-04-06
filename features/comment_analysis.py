"""
comment_analysis.py

功能：
    评论重复统计

技术：
    - Counter（词频统计）

修改时间：
    2026-04-06
"""

from collections import Counter


def top_repeated_comments(comments, top_n=10):
    """
    统计重复评论
    """

    counter = Counter([c["text"] for c in comments])

    return counter.most_common(top_n)
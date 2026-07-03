"""
visualization/report.py
生成情绪分析报告（JSON 格式）
不再生成 HTML/ECharts 可视化页面，所有统计结果汇总为 JSON 数据结构，
通过 utils.file_utils.save_report 保存到:
    data/report/{uname}/{title}/{bv_id}/{time_str}/report.json

修改时间：
    2026-06-27
-----------------------------
修改内容：
    generate_report 新增可选参数 time_str，透传给 save_report，
    保证 report.json 与同一次任务的其它产物落在同一个 {time_str}/ 目录下。
    不传时由 save_report 内部自行生成（向后兼容）。
"""

from __future__ import annotations
import pandas as pd

from utils import file_utils


# ------------------------------------------------------------------ helpers --

def _count_labels(df: pd.DataFrame, label_col: str) -> dict:
    if df.empty or label_col not in df.columns:
        return {"正向": 0, "中性": 0, "负向": 0}
    vc = df[label_col].value_counts()
    return {k: int(vc.get(k, 0)) for k in ["正向", "中性", "负向"]}


def _time_trend(df: pd.DataFrame, label_col: str) -> list[dict]:
    """评论按日期聚合的情绪时间趋势，返回 [{"date": str, "正向": n, "中性": n, "负向": n}, ...]"""
    if df.empty or "time" not in df.columns or label_col not in df.columns:
        return []

    tmp = df.dropna(subset=["time"]).copy()
    if tmp.empty:
        return []

    tmp["date"] = tmp["time"].dt.strftime("%Y-%m-%d")
    grp = tmp.groupby(["date", label_col]).size().unstack(fill_value=0)
    for col in ["正向", "中性", "负向"]:
        if col not in grp.columns:
            grp[col] = 0
    grp = grp.sort_index()

    return [
        {"date": date, "正向": int(row["正向"]), "中性": int(row["中性"]), "负向": int(row["负向"])}
        for date, row in grp.iterrows()
    ]


def _danmaku_timeline(df: pd.DataFrame) -> list[dict]:
    """弹幕情绪时间轴，返回 [{"video_sec": int, "score": float, "text": str}, ...]（最多 2000 条）"""
    score_col_candidates = ["snownlp_score", "bert_score"]
    if df.empty or "video_time" not in df.columns:
        return []

    sc_col = next((c for c in score_col_candidates if c in df.columns), None)
    if not sc_col:
        return []

    pts = df[["video_time", sc_col, "text_clean"]].dropna().head(2000)
    return [
        {
            "video_sec": int(row["video_time"]) // 1000,
            "score": round(float(row[sc_col]), 3),
            "text": str(row["text_clean"])[:50],
        }
        for _, row in pts.iterrows()
    ]


def _top_comments(df: pd.DataFrame, label_col: str, top_n: int = 10) -> list[dict]:
    """高赞评论 Top N"""
    if df.empty or "like" not in df.columns:
        return []

    top = df.nlargest(top_n, "like")[["text_clean", "like", label_col]].fillna("")
    return [
        {"text": r["text_clean"], "like": int(r["like"]), "label": r[label_col]}
        for _, r in top.iterrows()
    ]


# ------------------------------------------------------------------ main API --

def build_report_data(
    comments_df: pd.DataFrame,
    danmaku_df: pd.DataFrame,
    label_col: str,
    keywords_all: list[dict],
    keywords_pos: list[dict],
    keywords_neg: list[dict],
) -> dict:
    """汇总所有分析结果为一个 dict，供保存为 JSON"""

    return {
        "summary": {
            "comment_total": len(comments_df),
            "danmaku_total": len(danmaku_df),
            "comment_sentiment": _count_labels(comments_df, label_col),
            "danmaku_sentiment": _count_labels(danmaku_df, label_col),
        },
        "comment_time_trend": _time_trend(comments_df, label_col),
        "danmaku_timeline": _danmaku_timeline(danmaku_df),
        "keywords": {
            "all": keywords_all[:20],
            "positive": keywords_pos[:20],
            "negative": keywords_neg[:20],
        },
        "top_comments": _top_comments(comments_df, label_col, top_n=10),
    }


def generate_report(
    comments_df: pd.DataFrame,
    danmaku_df: pd.DataFrame,
    label_col: str,
    keywords_all: list[dict],
    keywords_pos: list[dict],
    keywords_neg: list[dict],
    bv_id: str,
    video_info: list,
    time_str: str | None = None,
) -> str:
    """
    生成情绪分析报告并保存为 JSON 文件
    bv_id, video_info 用于拼接保存路径:
        data/report/{uname}/{title}/{bv_id}/{time_str}/report.json
    video_info[0] = UID, video_info[1] = uname, video_info[2] = title
    time_str: 同一次任务统一的时间目录名，透传给 save_report；不传则内部生成。

    返回最终保存的文件路径
    """
    report_data = build_report_data(
        comments_df, danmaku_df, label_col,
        keywords_all, keywords_pos, keywords_neg,
    )
    return file_utils.save_report(report_data, bv_id, video_info, time_str=time_str)
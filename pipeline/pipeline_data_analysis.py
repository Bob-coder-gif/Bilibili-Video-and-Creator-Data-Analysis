"""
pipeline_data_analysis.py

视频统计数据分析管道（"分析阶段"统一出口）

修改时间：
    2026-06-23
----------------------------------
本阶段包含三件事：
    1. 视频统计数据保存 + 趋势图（save_video_stats）
    2. 舆情预警检测（warning_detector，需求 3）
    3. 话题聚类（topic_analyzer，需求 1，BERTopic）

数据来源：全部从上游 sentiment_pipeline(task) 传入的 task 字典读取，不依赖全局变量。
需要用到的 task 字段：
    bv_id / video_info / stat          —— crawler_pipeline 写入
    sentiment_summary                   —— sentiment_pipeline 写入（预警用）
    comment_texts / comment_labels      —— sentiment_pipeline 写入（话题聚类用）
    time_str                            —— crawler_pipeline 写入（统一时间目录）

执行顺序说明：
    必须先 save_video_stats（把本次 stat 追加进历史记录并落盘），
    再 record_sentiment_summary（把情绪摘要补写进刚追加的那条记录），
    最后 detect_warnings（基于完整历史记录算预警）。顺序不能乱。

修改时间：
    2026-06-27
----------------------------------
    新增可选 progress 回调：在统计趋势 / 预警 / 话题聚类节点汇报进度，
    供网页后台任务实时显示。progress=None 时跳过。

用法（app.main 等入口文件里）：
    task = pipeline.crawler_pipeline.crawler_pipeline(bv_id)
    task = pipeline.sentiment_pipeline.sentiment_pipeline(task)
    task = pipeline.pipeline_data_analysis.pipeline_data_analysis(task)
================================
"""

from __future__ import annotations

from analyzer.video_stats import save_video_stats, get_history
from analyzer.warning_detector import (
    record_sentiment_summary,
    detect_warnings,
    save_warnings,
)
from analyzer.topic_analyzer import run_topic_analysis
import config.config as cfg
from utils.log_utils import get_logger, log_event

logger = get_logger()


def _report(progress, stage, message="", **extra):
    """安全调用进度回调：progress 为 None 时什么也不做"""
    if progress is not None:
        progress(stage, message, **extra)


def pipeline_data_analysis(task: dict | None = None, progress=None) -> dict:
    """
    分析阶段入口。从 task 读取数据，依次完成统计/预警/话题聚类，结果写回 task 并落盘。

    参数:
        task: 上游 sentiment_pipeline 返回的 task 字典。
        progress: 可选进度回调；None 时不汇报。

    返回更新后的 task，新增字段:
        video_stats_result   视频统计/趋势图结果
        warnings             预警列表
        warnings_path        预警结果文件路径
        topic_result         话题聚类结果（数据不足/未装 BERTopic 时为 None）
    """
    if task is None:
        task = {}

    bv_id = task.get("bv_id") or cfg.CURRENT_BV_ID
    video_info = task.get("video_info") or cfg.CURRENT_VIDEO_INFO
    stat = task.get("stat", {})

    if not bv_id or not video_info:
        logger.warning(
            "task 中没有当前视频信息，请确认 crawler_pipeline() 已先于本管道运行。跳过本次分析。"
        )
        log_event("data_analysis_skipped", reason="missing_bv_id_or_video_info")
        return task

    time_str = task.get("time_str")

    # ---------- 1. 视频统计数据 + 趋势图 ----------
    _report(progress, "analysis", "正在统计视频数据趋势…")
    if not stat:
        logger.warning("当前视频 stat 数据为空，stat 数据将全部按 0 保存。")
        log_event("data_analysis_stat_empty", bv_id=bv_id)

    result = save_video_stats(bv_id=bv_id, video_info=video_info, stat=stat, time_str=time_str)
    log_event(
        "video_stats_saved",
        bv_id=bv_id,
        point_count=result["point_count"],
        snapshot_path=result["snapshot_path"],
        history_path=result["history_path"],
        trend_image_path=result["trend_image_path"],
    )
    if result["trend_image_path"]:
        logger.info(
            f"📈 趋势图已更新（当前累计 {result['point_count']} 个数据点）: "
            f"{result['trend_image_path']}"
        )
    else:
        need = cfg.MIN_POINTS_FOR_TREND
        logger.info(
            f"ℹ️  当前累计 {result['point_count']} 个数据点，"
            f"再抓取 {max(0, need - result['point_count'])} 次后即可生成趋势图"
        )
    task["video_stats_result"] = result

    # ---------- 2. 舆情预警 ----------
    _report(progress, "analysis", "正在进行舆情预警检测…")
    # 先把本次情绪摘要补写进刚刚追加的那条历史记录（save_video_stats 已追加该记录）
    sentiment_summary = task.get("sentiment_summary") or {}
    if sentiment_summary:
        record_sentiment_summary(bv_id, video_info, sentiment_summary)

    # 重新读出完整历史（含刚写入的情绪摘要），再做预警检测
    history = get_history(bv_id, video_info)
    warnings = detect_warnings(history)
    warnings_path = save_warnings(bv_id, video_info, warnings, time_str=time_str)
    task["warnings"] = warnings
    task["warnings_path"] = warnings_path

    # ---------- 3. 话题聚类 ----------
    # 数据不足 / 未装 BERTopic 时 run_topic_analysis 返回 None，不影响主流程
    _report(progress, "analysis", "正在进行话题聚类…")
    comment_texts = task.get("comment_texts") or []
    comment_labels = task.get("comment_labels")
    topic_result = run_topic_analysis(
        texts=comment_texts,
        bv_id=bv_id,
        video_info=video_info,
        labels=comment_labels,
        time_str=time_str,
    )
    task["topic_result"] = topic_result

    return task


if __name__ == "__main__":
    pipeline_data_analysis(None)
"""
pipeline_data_analysis.py

视频统计数据分析管道

修改时间：
    2026-06-21
----------------------------------

与 crawler_pipeline() / sentiment_pipeline() 保持同样的调用方式：
无参数，数据通过 config 模块传递。

依赖（由 crawler_pipeline() 在抓取阶段写入）：
    config.CURRENT_BV_ID     当前视频 BV 号
    config.CURRENT_VIDEO_INFO  [UID, uname, title]
    config.CURRENT_VIDEO_STAT  视频 stat 字典（在 get_video_info() 里顺手抓取写入）

用法（app.main 等入口文件里）：

    if __name__ == "__main__":
        pipeline.crawler_pipeline.crawler_pipeline()
        pipeline.sentiment_pipeline.sentiment_pipeline()
        pipeline.pipeline_data_analysis.pipeline_data_analysis()
================================
        
"""

from __future__ import annotations

from analyzer.video_stats import save_video_stats
import config.config as cfg
from utils.log_utils import get_logger, log_event

logger = get_logger()


def pipeline_data_analysis():
    """
    视频统计数据分析管道入口：
      1. 从 config 黑板读取本次的 bv_id / video_info / stat
      2. 保存本次快照 JSON
      3. 追加进该视频的历史记录 JSON（动态累积，每次在上一次基础上添加）
      4. 历史记录足够时（默认 >=2 条）自动生成/更新趋势图 PNG
    """
    bv_id = cfg.CURRENT_BV_ID
    video_info = cfg.CURRENT_VIDEO_INFO
    stat = cfg.CURRENT_VIDEO_STAT

    if not bv_id or not video_info:
        # 缺前置条件，属于真正异常，终端必须看到
        logger.warning(
            "config 中没有当前视频信息，请确认 crawler_pipeline() 已先于本管道运行。跳过本次分析。"
        )
        log_event("data_analysis_skipped", reason="missing_bv_id_or_video_info")
        return None

    if not stat:
        logger.warning("config.CURRENT_VIDEO_STAT 为空，stat 数据将全部按 0 保存。")
        log_event("data_analysis_stat_empty", bv_id=bv_id)

    result = save_video_stats(bv_id=bv_id, video_info=video_info, stat=stat)

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

    return result
"""
pipeline/crawler_pipeline.py
采集阶段：爬评论 → 获取视频信息 → 爬弹幕 → 弹幕可视化

修改时间：
    2026-06-22
----------------------------------
    crawler_pipeline() 改为显式接收 bv_id、返回 task 字典，由调用方一路往下传给
    sentiment_pipeline(task) / pipeline_data_analysis(task)，不再写 config 全局变量。

修改时间：
    2026-06-27
----------------------------------
    1. 移除高频评论统计与可视化。
    2. 新增 time_str：同一次任务的全部产物落在同一个 {time_str}/ 目录下。
    3. 新增可选 progress 回调，供网页后台任务汇报进度。

修改时间：
    2026-09-28
----------------------------------
    1. 删除 __main__ 测试入口（交互式选测试 BV 号，已由网页入口取代）。
    2. 删除与 fetch_comments / fetch_danmu 内部重复的日志和 log_event
       （原来"开始爬取弹幕"、"共获取到 N 条弹幕"等每次都打印两遍）。
"""

from collections import Counter
from datetime import datetime

from crawler.fetch_comments import fetch_comments
from crawler.fetch_danmu import fetch_danmu
from crawler.get_info_from_browser import get_video_info
from utils.file_utils import save_comments, save_danmu
from utils.log_utils import get_logger, log_event
from visualization.danmu_vis import plot_top_danmu, plot_danmu_density, plot_danmu_wordcloud

logger = get_logger()


def _report(progress, stage, message="", **extra):
    """安全调用进度回调：progress 为 None 时什么也不做"""
    if progress is not None:
        progress(stage, message, **extra)


def crawler_pipeline(bv_id: str, progress=None) -> dict:
    """
    采集阶段入口。

    返回 task 字典，供后续 pipeline 使用：
        bv_id, video_info=[uid, uname, title], comments, danmus,
        comments_path, danmaku_path, stat, time_str
    """
    time_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    comments, video_info, comments_path, stat = fetch_and_save_comments(bv_id, time_str, progress)
    danmus, danmaku_path = fetch_and_save_danmu(bv_id, video_info, time_str, progress)
    visualize_danmu(danmus, bv_id, video_info, time_str, progress)

    logger.info("✅ 爬取与可视化全部完成！")
    return {
        "bv_id": bv_id,
        "video_info": video_info,
        "comments": comments,
        "danmus": danmus,
        "comments_path": comments_path,
        "danmaku_path": danmaku_path,
        "stat": stat,
        "time_str": time_str,
    }


def fetch_and_save_comments(bv_id: str, time_str: str, progress=None) -> tuple:
    """爬取并保存评论。返回 (comments, video_info, comments_path, stat)"""
    log_event("fetch_comments_start", bv_id=bv_id)

    # 实时条数由 fetch_comments 内部通过 progress 汇报
    comments = fetch_comments(bv_id, max_count=0, progress=progress)

    # fetch_comments 打开视频页时已缓存视频信息，这里通常不会再发请求
    video_info, stat = get_video_info(bv_id)

    comments_path = save_comments(bv_id, video_info, comments, time_str=time_str)
    return comments, video_info, comments_path, stat


def fetch_and_save_danmu(bv_id: str, video_info: list, time_str: str, progress=None) -> tuple:
    """爬取并保存弹幕。返回 (danmus, danmaku_path)"""
    _report(progress, "crawl_danmu", "正在爬取弹幕…")

    danmus = fetch_danmu(bv_id)
    danmaku_path = save_danmu(bv_id, video_info, danmus, time_str=time_str)

    _report(progress, "crawl_danmu", f"弹幕爬取完成，共 {len(danmus)} 条", danmu_count=len(danmus))
    return danmus, danmaku_path


def visualize_danmu(danmus: list[dict], bv_id: str, video_info: list,
                    time_str: str, progress=None):
    """统计高频弹幕 + 生成三张图。弹幕为空时跳过。"""
    if not danmus:
        logger.warning("弹幕列表为空，跳过弹幕可视化")
        log_event("danmu_empty", bv_id=bv_id)
        return

    _report(progress, "visualize", "正在生成弹幕可视化图表…")

    top_danmu = Counter(d["text"] for d in danmus if d.get("text")).most_common(10)
    log_event("top_danmu", bv_id=bv_id, top10=top_danmu)

    plot_top_danmu(top_danmu, bv_id, video_info, time_str=time_str)
    plot_danmu_density(danmus, bv_id, video_info, time_str=time_str)
    plot_danmu_wordcloud(danmus, bv_id, video_info, time_str=time_str)
    logger.info("弹幕可视化已完成")

"""
crawler_pipeline.py

爬虫管道

修改时间：
    2026-06-22
----------------------------------
重构说明（第二阶段第一步）：
    crawler_pipeline() 原本无参数，靠交互式 input() 选 bv_id，
    完成后把 bv_id / video_info 写回 config 模块的全局变量。
    这种"黑板"模式在并发时会数据串台，改为显式接收 bv_id、返回 task 字典，
    由调用方一路往下传给 sentiment_pipeline(task) / pipeline_data_analysis(task)。

修改时间：
    2026-06-27
----------------------------------
    1. 移除高频评论统计与可视化（删 analysis_comments 及相关 import / 调用）。
    2. 新增 time_str：管道开头生成统一时间目录名，传给所有保存/画图函数，
       保证同一次任务全部产物落在同一个 {time_str}/ 目录下。
    3. 新增可选 progress 回调：网页后台任务跑此管道时传入，管道在关键节点
       调用 progress(stage, message, **extra) 汇报进度。其中评论实时条数由
       fetch_comments 内部直接通过 progress 汇报（“正在爬取评论…已 N 条”）。
       命令行直接调用时 progress=None，汇报自动跳过。
"""

from crawler.fetch_comments import fetch_comments
from utils.file_utils import save_comments, save_danmu
from crawler.get_info_from_browser import get_video_info
from crawler.fetch_danmu import fetch_danmu
from visualization.danmu_vis import plot_top_danmu, plot_danmu_density, plot_danmu_wordcloud
from collections import Counter
from utils.log_utils import get_logger, log_event
from datetime import datetime


logger = get_logger()


def _report(progress, stage, message="", **extra):
    """安全调用进度回调：progress 为 None 时什么也不做（命令行单独跑即为 None）"""
    if progress is not None:
        progress(stage, message, **extra)


def crawler_pipeline(bv_id: str, progress=None) -> dict:
    """
    爬虫管道入口：负责调用各个爬虫模块进行数据抓取。

    参数:
        bv_id   : 要抓取的视频 BV 号
        progress: 可选进度回调；None 时不汇报。

    返回:
        task 字典，包含本次任务的上下文，供后续 pipeline 使用：
        {
            "bv_id": str, "video_info": [uid, uname, title],
            "comments": dict, "danmus": list,
            "comments_path": str, "danmaku_path": str,
            "stat": dict, "time_str": str,
        }
    """
    time_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    comments, video_info, comments_path, stat = fetch_and_save_comments(bv_id, time_str, progress)
    danmus, danmaku_path = fetch_and_save_danmu(bv_id, video_info, time_str, progress)
    analysis_and_visualization_danmu(danmus, bv_id, video_info, time_str, progress)

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


def fetch_and_save_comments(bv_id: str, time_str: str = None, progress=None) -> tuple:
    """
    爬取并保存评论。返回 (comments, video_info, comments_path, stat)。
    评论的实时条数进度由 fetch_comments 内部直接通过 progress 汇报。
    """
    logger.info("开始爬取评论...")
    log_event("fetch_comments_start", bv_id=bv_id)

    # progress 传进 fetch_comments，让它在滚动爬取过程中实时汇报已收集条数
    comments = fetch_comments(bv_id, max_count=0, progress=progress)

    # 获取视频信息（get_video_info 现在返回 (video_info, stat) 两个值）
    video_info, stat = get_video_info(bv_id)

    comments_path = save_comments(bv_id, video_info, comments, time_str=time_str)

    logger.info(f"主评论抓取完成，共收集 {len(comments)} 条评论")
    log_event("fetch_comments_done", bv_id=bv_id, count=len(comments))

    return comments, video_info, comments_path, stat


def fetch_and_save_danmu(bv_id: str, video_info: tuple, time_str: str = None, progress=None) -> tuple:
    """爬取并保存弹幕。返回 (danmus, danmaku_path)。"""
    logger.info("开始爬取弹幕...")
    log_event("fetch_danmu_start", bv_id=bv_id)
    _report(progress, "crawl_danmu", "正在爬取弹幕…")

    danmus = fetch_danmu(bv_id)
    logger.info(f"共获取到 {len(danmus)} 条弹幕")

    danmaku_path = save_danmu(bv_id, video_info, danmus, time_str=time_str)
    log_event("fetch_danmu_done", bv_id=bv_id, count=len(danmus))
    _report(progress, "crawl_danmu", f"弹幕爬取完成，共 {len(danmus)} 条", danmu_count=len(danmus))

    return danmus, danmaku_path


def analysis_and_visualization_danmu(danmus: list[dict], bv_id: str, video_info: tuple,
                                     time_str: str = None, progress=None):
    """弹幕侧分析与可视化：统计高频弹幕词条 + 生成三张图。弹幕为空时跳过。"""
    if not danmus:
        logger.warning("弹幕列表为空，跳过分析")
        log_event("danmu_empty", bv_id=bv_id)
        return

    _report(progress, "visualize", "正在生成弹幕可视化图表…")

    counter = Counter(d["text"] for d in danmus if d.get("text"))
    top_danmu = counter.most_common(10)

    logger.debug(f"高频弹幕 TOP10: {top_danmu}")
    log_event("top_danmu", bv_id=bv_id, top10=top_danmu)
    logger.info(f"已统计高频弹幕 TOP{len(top_danmu)}")

    plot_top_danmu(top_danmu, bv_id, video_info, time_str=time_str)
    plot_danmu_density(danmus, bv_id, video_info, time_str=time_str)
    plot_danmu_wordcloud(danmus, bv_id, video_info, time_str=time_str)
    logger.info("弹幕可视化已完成")


# ------------------------------------------------------------------ CLI ----

if __name__ == "__main__":
    test_bv_id = [
        "BV1uPDTBhEHX",  # 饼叔巴尔干
        "BV15edfB8EK1",  # 央视新闻
        "BV1kZ4y147Fi",  # 死水bug
        "BV1834y1D7L8",  # 纲手
        "BV1LzrSBNEWi",  # 评论回复超过一页
        "BV1zu411R7os",  # 测试弹幕
        "BV1Lvo2BNEZz",  # 何以当归reaction预告
    ]
    chosen_bv_id = test_bv_id[int(input("测试序号（0-6）: "))]
    crawler_pipeline(chosen_bv_id)
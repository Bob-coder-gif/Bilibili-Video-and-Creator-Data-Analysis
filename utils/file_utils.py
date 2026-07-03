import json
from pathlib import Path
from datetime import datetime
import config.config as cfg
import os
import pandas as pd
from utils.log_utils import get_logger, log_event

logger = get_logger()

'''
file_utils.py
功能：
    文件操作工具函数

修改时间：
    2026-06-27
-----------------------------
修改内容（路径结构调整）：
    保存路径从"文件名里塞 bv_id 和时间"改为"bv_id 和时间作为目录层级"：
        旧: data/report/{uname}/{title}/{bv_id}_{time}_xxx.json
        新: data/report/{uname}/{title}/{bv_id}/{time}/xxx.json

    所有 save_* 函数新增可选参数 time_str：
      - 由上游 crawler_pipeline 在任务开始时生成一个统一的 time_str，
        通过 task 传给本次任务的所有 save_* 调用，保证同一次任务的全部产物
        落在同一个 {time}/ 目录下，不会因为各函数调用时刻不同而散落。
      - 不传 time_str（=None）时，函数内部自己 datetime.now() 生成一个，
        保持向后兼容，漏传也不会报错（只是那个产物会单独进一个时间目录）。
'''


def _time_str(time_str: str | None) -> str:
    """没传统一时间就现生成一个；传了就用传入的，保证同一次任务目录一致"""
    return time_str or datetime.now().strftime("%Y%m%d_%H%M%S")


def _report_dir(uname: str, title: str, bv_id: str, time_str: str) -> Path:
    """data/report/{uname}/{title}/{bv_id}/{time_str}/ ，自动创建"""
    d = Path("data/report") / uname / title / bv_id / time_str
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_profile(profile, bv_id: str):
    """保存UP主信息（分类版）"""
    save_dir = Path("data/raw/profile")
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / f"{bv_id}_profile.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
    logger.debug(f"UP主信息已保存: {file_path}")
    log_event("profile_saved", bv_id=bv_id, path=str(file_path))


def load_profile(path: Path):
    from models.video import UploaderProfile
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return UploaderProfile.from_dict(data)


def save_comments(bv_id: str, video_info: list, comments: list, time_str: str | None = None) -> str:
    """
    保存评论数据（带时间版本）
    video_info[0]=UID  [1]=uname  [2]=title
    新路径: data/raw/comments/{uname}/{title}/{bv_id}/{time_str}/comments.json
    返回保存后的文件路径（字符串）
    """
    now = datetime.now()
    time_str = _time_str(time_str)

    uid, uname, title = video_info[0], video_info[1], video_info[2]

    data = {
        "name": uname, "bv_id": bv_id, "uid": uid, "uname": uname, "title": title,
        "crawl_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "comment_count": len(comments),
        "comments": comments,
    }

    save_dir = Path(f"data/raw/comments/{uname}/{title}/{bv_id}/{time_str}")
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / "comments.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.debug(f"评论数据已保存: {file_path}")

    cfg.COMMENTS_FILE = f"{cfg.COMMENTS_DIR}/{uname}/{title}/{bv_id}/{time_str}/comments.json"
    logger.debug(f"更新全局配置: cfg.COMMENTS_FILE = {cfg.COMMENTS_FILE}")

    log_event("comments_saved", bv_id=bv_id, path=str(file_path), comment_count=len(comments))
    return str(file_path)


def save_danmu(bv_id: str, video_info: list, danmus: list, time_str: str | None = None) -> str:
    """
    保存弹幕数据
    新路径: data/raw/danmu/{uname}/{title}/{bv_id}/{time_str}/danmu.json
    返回保存后的文件路径（字符串）
    """
    now = datetime.now()
    time_str = _time_str(time_str)

    uid, uname, title = video_info[0], video_info[1], video_info[2]

    data = {
        "name": uname, "bv_id": bv_id, "uid": uid, "uname": uname, "title": title,
        "crawl_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "danmu_count": len(danmus),
        "danmus": danmus,
    }

    save_dir = Path(f"data/raw/danmu/{uname}/{title}/{bv_id}/{time_str}")
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / "danmu.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.debug(f"弹幕数据已保存: {file_path}")

    cfg.DANMAKU_FILE = f"{cfg.DANMAKU_DIR}/{uname}/{title}/{bv_id}/{time_str}/danmu.json"
    logger.debug(f"更新全局配置: cfg.DANMAKU_FILE = {cfg.DANMAKU_FILE}")

    log_event("danmu_saved", bv_id=bv_id, path=str(file_path), danmu_count=len(danmus))
    return str(file_path)


def save_report(report_data: dict, bv_id: str, video_info: list, time_str: str | None = None) -> str:
    """
    保存情绪分析报告（JSON）
    新路径: data/report/{uname}/{title}/{bv_id}/{time_str}/report.json
    返回保存后的文件路径（字符串）
    """
    now = datetime.now()
    time_str = _time_str(time_str)
    uid, uname, title = video_info[0], video_info[1], video_info[2]

    data = {
        "name": uname, "bv_id": bv_id, "uid": uid, "uname": uname, "title": title,
        "report_time": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    data.update(report_data)

    save_dir = _report_dir(uname, title, bv_id, time_str)
    file_path = save_dir / "report.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.debug(f"分析报告已保存: {file_path}")
    return str(file_path)


def save_word_freq(freq: dict, bv_id: str, video_info: list, time_str: str | None = None) -> str:
    """
    保存关键词词频统计（JSON）
    新路径: data/report/{uname}/{title}/{bv_id}/{time_str}/word_freq.json
    返回保存后的文件路径（字符串）
    """
    time_str = _time_str(time_str)
    uname, title = video_info[1], video_info[2]

    save_dir = _report_dir(uname, title, bv_id, time_str)
    file_path = save_dir / "word_freq.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(freq, f, ensure_ascii=False, indent=2)
    logger.debug(f"词频统计已保存: {file_path}")
    return str(file_path)


def save_results(df: pd.DataFrame, name: str, bv_id: str, video_info: list, time_str: str | None = None) -> str:
    """
    保存带情绪标签的标注结果 + 统计摘要
    name 区分 comments / danmaku
    新路径: data/report/{uname}/{title}/{bv_id}/{time_str}/{name}_annotated.json
            data/report/{uname}/{title}/{bv_id}/{time_str}/{name}_summary.json
    返回标注结果文件的路径（字符串）
    """
    time_str = _time_str(time_str)
    uname, title = video_info[1], video_info[2]

    save_dir = _report_dir(uname, title, bv_id, time_str)

    annotated_path = save_dir / f"{name}_annotated.json"
    df.to_json(annotated_path, orient="records", force_ascii=False, indent=2)
    logger.debug(f"[save] {name} 已保存: {annotated_path}")

    summary = {}
    for col in df.columns:
        if col.endswith("_label"):
            summary[col] = df[col].value_counts().to_dict()
    summary_path = save_dir / f"{name}_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.debug(f"[save] 摘要已保存: {summary_path}")

    return str(annotated_path)
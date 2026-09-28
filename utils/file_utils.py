"""
utils/file_utils.py
文件保存工具 + 统一的产物目录拼接

目录约定：
    {根目录}/{uname}/{title}/{bv_id}/{time_str}/xxx
    同一次任务的所有产物使用 crawler_pipeline 生成的同一个 time_str；
    不传 time_str 时内部现生成一个（向后兼容）。

2026-06-27 修改：
    bv_id 和时间从文件名改为目录层级；所有 save_* 新增可选参数 time_str。

2026-09-28 修改：
    1. 新增 safe_name / video_dir：所有模块统一用它拼目录。
       原来直接把 uname / title 当目录名，B 站标题里常见的 | ? : " * < > 等字符
       在 Windows 上是非法文件名，会直接让任务报错；标题里的 / 还会多拆出一层目录，
       导致网页按 */*/{bv_id} 查找历史时找不到。
    2. 删除 save_profile / load_profile（UP 主预测项目遗留，依赖已删除的 models 包）。
    3. 删除 save_comments / save_danmu 里对 cfg.COMMENTS_FILE / DANMAKU_FILE
       的全局变量写入（"黑板"模式遗留，已无读取方）。
    4. 根目录改从 config 读取，不再写死 "data/report" 等字符串。
"""

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

import config.config as cfg
from utils.log_utils import get_logger, log_event

logger = get_logger()


# ------------------------------------------------------------------ paths --

# Windows 文件名非法字符 + 控制字符
_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
# Windows 保留设备名
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL",
                   *(f"COM{i}" for i in range(1, 10)),
                   *(f"LPT{i}" for i in range(1, 10))}
_MAX_NAME_LEN = 80   # B 站标题上限 80 字，正常标题不会被截断


def safe_name(name, fallback: str = "unknown") -> str:
    """把 uname / title 转成可以安全用作目录名的字符串"""
    s = _ILLEGAL_CHARS.sub("_", str(name or "")).strip()
    s = s[:_MAX_NAME_LEN].rstrip(". ")   # Windows 不允许以点或空格结尾
    if not s:
        return fallback
    if s.upper() in _RESERVED_NAMES:
        s = f"_{s}"
    return s


def video_dir(root, video_info, bv_id: str, time_str: str | None = None) -> Path:
    """
    拼接并创建 {root}/{uname}/{title}/{bv_id}[/{time_str}]/
    video_info = [uid, uname, title]
    """
    d = Path(root) / safe_name(video_info[1]) / safe_name(video_info[2]) / bv_id
    if time_str:
        d = d / time_str
    d.mkdir(parents=True, exist_ok=True)
    return d


def _time_str(time_str: str | None) -> str:
    """没传统一时间就现生成一个"""
    return time_str or datetime.now().strftime("%Y%m%d_%H%M%S")


def _meta(bv_id: str, video_info: list) -> dict:
    uid, uname, title = video_info[0], video_info[1], video_info[2]
    return {"name": uname, "bv_id": bv_id, "uid": uid, "uname": uname, "title": title}


def _dump(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ save ---

def save_comments(bv_id: str, video_info: list, comments: dict, time_str: str | None = None) -> str:
    """保存原始评论：data/raw/comments/{uname}/{title}/{bv_id}/{time_str}/comments.json"""
    data = {
        **_meta(bv_id, video_info),
        "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "comment_count": len(comments),
        "comments": comments,
    }
    path = video_dir(cfg.COMMENTS_DIR, video_info, bv_id, _time_str(time_str)) / "comments.json"
    _dump(path, data)
    logger.debug(f"评论数据已保存: {path}")
    log_event("comments_saved", bv_id=bv_id, path=str(path), comment_count=len(comments))
    return str(path)


def save_danmu(bv_id: str, video_info: list, danmus: list, time_str: str | None = None) -> str:
    """保存原始弹幕：data/raw/danmu/{uname}/{title}/{bv_id}/{time_str}/danmu.json"""
    data = {
        **_meta(bv_id, video_info),
        "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "danmu_count": len(danmus),
        "danmus": danmus,
    }
    path = video_dir(cfg.DANMAKU_DIR, video_info, bv_id, _time_str(time_str)) / "danmu.json"
    _dump(path, data)
    logger.debug(f"弹幕数据已保存: {path}")
    log_event("danmu_saved", bv_id=bv_id, path=str(path), danmu_count=len(danmus))
    return str(path)


def save_report(report_data: dict, bv_id: str, video_info: list, time_str: str | None = None) -> str:
    """保存情绪分析报告：data/report/{uname}/{title}/{bv_id}/{time_str}/report.json"""
    data = {**_meta(bv_id, video_info),
            "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    data.update(report_data)
    path = video_dir(cfg.OUTPUT_DIR, video_info, bv_id, _time_str(time_str)) / "report.json"
    _dump(path, data)
    logger.debug(f"分析报告已保存: {path}")
    return str(path)


def save_word_freq(freq: list, bv_id: str, video_info: list, time_str: str | None = None) -> str:
    """保存词频统计：data/report/{uname}/{title}/{bv_id}/{time_str}/word_freq.json"""
    path = video_dir(cfg.OUTPUT_DIR, video_info, bv_id, _time_str(time_str)) / "word_freq.json"
    _dump(path, freq)
    logger.debug(f"词频统计已保存: {path}")
    return str(path)


def save_results(df: pd.DataFrame, name: str, bv_id: str, video_info: list,
                 time_str: str | None = None) -> str:
    """
    保存带情绪标签的标注结果 + 标签计数摘要（name 区分 comments / danmaku）：
        .../{time_str}/{name}_annotated.json
        .../{time_str}/{name}_summary.json
    返回标注结果文件路径
    """
    save_dir = video_dir(cfg.OUTPUT_DIR, video_info, bv_id, _time_str(time_str))

    annotated_path = save_dir / f"{name}_annotated.json"
    df.to_json(annotated_path, orient="records", force_ascii=False, indent=2, date_format="iso")

    summary = {col: df[col].value_counts().to_dict()
               for col in df.columns if col.endswith("_label")}
    _dump(save_dir / f"{name}_summary.json", summary)

    logger.debug(f"[save] {name} 标注结果与摘要已保存: {save_dir}")
    return str(annotated_path)

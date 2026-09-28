"""
utils/loader.py
加载 crawler 保存的评论 / 弹幕 JSON，统一转成 DataFrame

2026-09-28 修改：
    1. 评论的楼中楼回复现在也会被加载（source="reply"）。
       原来只读主评论，fetch_comments 花几百个请求抓回来的回复在分析里完全没被用到。
    2. 弹幕的 video_time 改为保存原始秒数（float）。
       原来按"毫秒"处理：先 int() 截断成整数秒，report 里再 //1000，
       结果所有弹幕的 video_sec 都是 0，弹幕情绪时间轴完全失效。
    3. 删除 load_meta（只给已删除的命令行入口用）。
"""

import json
import os
from datetime import datetime

import pandas as pd

from utils.log_utils import get_logger

logger = get_logger()


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_timestamp(value) -> datetime | None:
    """Unix 时间戳 -> datetime，兼容毫秒级；无效值返回 None"""
    if not value:
        return None
    try:
        ts = int(value)
        if ts > 1e10:      # 毫秒
            ts = ts / 1000
        return datetime.fromtimestamp(ts)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _comment_row(item_id, item: dict, source: str, cfg) -> dict | None:
    text = str(item.get(cfg.COMMENT_TEXT_FIELD, "") or "").strip()
    if not text:
        return None
    return {
        "id":     str(item_id),
        "text":   text,
        "time":   _parse_timestamp(item.get(cfg.COMMENT_TIME_FIELD)),
        "like":   int(item.get(cfg.COMMENT_LIKE_FIELD, 0) or 0),
        "user":   item.get(cfg.COMMENT_USER_FIELD, ""),
        "source": source,
    }


def load_comments(path: str, cfg) -> pd.DataFrame:
    """
    加载评论文件（主评论 + 回复展开成同一张表）
    列: id, text, time, like, user, source("comment" / "reply")
    """
    if not os.path.exists(path):
        logger.warning(f"评论文件不存在: {path}")
        return pd.DataFrame()

    comments = _read_json(path).get("comments") or {}
    rows = []
    for rpid, c in comments.items():
        row = _comment_row(rpid, c, "comment", cfg)
        if row:
            rows.append(row)
        for i, r in enumerate(c.get("replies") or []):
            row = _comment_row(f"{rpid}_r{i}", r, "reply", cfg)
            if row:
                rows.append(row)

    df = pd.DataFrame(rows)
    logger.debug(f"[loader] 加载评论 {len(df)} 条（含回复）")
    return df


def load_danmaku(path: str, cfg) -> pd.DataFrame:
    """
    加载弹幕文件
    列: id, text, video_time(秒, float), source
    """
    if not os.path.exists(path):
        logger.warning(f"弹幕文件不存在: {path}")
        return pd.DataFrame()

    rows = []
    for d in _read_json(path).get("danmus") or []:
        text = str(d.get(cfg.DANMAKU_TEXT_FIELD, "") or "").strip()
        if not text:
            continue
        rows.append({
            "id":         d.get(cfg.DANMAKU_ID_FIELD, ""),
            "text":       text,
            "video_time": float(d.get(cfg.DANMAKU_TIME_FIELD, 0) or 0),
            "source":     "danmaku",
        })

    df = pd.DataFrame(rows)
    logger.debug(f"[loader] 加载弹幕 {len(df)} 条")
    return df

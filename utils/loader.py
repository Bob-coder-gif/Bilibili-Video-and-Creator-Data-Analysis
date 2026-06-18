"""
utils/loader.py
负责加载评论 / 弹幕 JSON，统一转成内部 DataFrame 格式
"""

import json
import os
import pandas as pd
from datetime import datetime
import config.config as cfg

def _load_json(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    rows = []
    
    # 情况1: 处理评论文件 (包含 "comments" 对象)
    if "comments" in data and isinstance(data["comments"], dict):
        for comment_id, comment_data in data["comments"].items():
            # 提取基础信息
            text = comment_data.get(cfg.COMMENT_TEXT_FIELD, "")
            if not text:
                continue
                
            # 构建记录
            record = {
                cfg.COMMENT_ID_FIELD: comment_id, # 使用 JSON 的 key 作为 ID
                cfg.COMMENT_TEXT_FIELD: str(text).strip(),
                cfg.COMMENT_TIME_FIELD: comment_data.get(cfg.COMMENT_TIME_FIELD),
                cfg.COMMENT_LIKE_FIELD: comment_data.get(cfg.COMMENT_LIKE_FIELD, 0),
                cfg.COMMENT_USER_FIELD: comment_data.get(cfg.COMMENT_USER_FIELD, ""),
                "source": "comment",
            }
            rows.append(record)
    
    # 情况2: 处理弹幕文件 (包含 "danmus" 列表)
    elif "danmus" in data and isinstance(data["danmus"], list):
        for item in data["danmus"]:
            text = item.get(cfg.DANMAKU_TEXT_FIELD, "")
            if not text:
                continue
                
            # 注意: 弹幕时间单位是 秒 (float)，loader.py 里默认是毫秒
            # 所以这里直接存 float，后面在 load_danmaku 里处理
            record = {
                cfg.DANMAKU_ID_FIELD: item.get(cfg.DANMAKU_ID_FIELD, ""),
                cfg.DANMAKU_TEXT_FIELD: str(text).strip(),
                cfg.DANMAKU_TIME_FIELD: item.get(cfg.DANMAKU_TIME_FIELD), # 单位: 秒
                "source": "danmaku",
            }
            rows.append(record)
    
    return rows

def load_comments(path: str, cfg) -> pd.DataFrame:
    """
    加载评论文件，返回标准化 DataFrame
    列: id, text, time, like, user
    """
    if not os.path.exists(path):
        print(f"[警告] 评论文件不存在: {path}")
        return pd.DataFrame()

    records = _load_json(path)
    rows = []
    for r in records:
        text = r.get(cfg.COMMENT_TEXT_FIELD, "")
        if not text:
            continue
        rows.append({
            "id":   r.get(cfg.COMMENT_ID_FIELD, ""),
            "text": str(text).strip(),
            "time": _parse_timestamp(r.get(cfg.COMMENT_TIME_FIELD)),
            "like": int(r.get(cfg.COMMENT_LIKE_FIELD, 0) or 0),
            "user": r.get(cfg.COMMENT_USER_FIELD, ""),
            "source": "comment",
        })
    df = pd.DataFrame(rows)
    print(f"[loader] 加载评论 {len(df)} 条")
    return df


def load_danmaku(path: str, cfg) -> pd.DataFrame:
    """
    加载弹幕文件，返回标准化 DataFrame
    列: id, text, video_time, source
    """
    if not os.path.exists(path):
        print(f"[警告] 弹幕文件不存在: {path}")
        return pd.DataFrame()

    records = _load_json(path)
    rows = []
    for r in records:
        text = r.get(cfg.DANMAKU_TEXT_FIELD, "")
        if not text:
            continue
        rows.append({
            "id":         r.get(cfg.DANMAKU_ID_FIELD, ""),
            "text":       str(text).strip(),
            "video_time": int(r.get(cfg.DANMAKU_TIME_FIELD, 0) or 0),  # ms
            "source":     "danmaku",
        })
    df = pd.DataFrame(rows)
    print(f"[loader] 加载弹幕 {len(df)} 条")
    return df


def load_meta(path: str) -> dict:
    """
    从评论 JSON 顶层读取元信息（uname / title / bv_id 等）
    用于 report 阶段拼接输出路径: data/report/{uname}/{title}/{bv_id}_{time_str}_report.json
    若文件不存在或字段缺失，对应值返回空字符串
    """
    if not os.path.exists(path):
        print(f"[警告] 元信息文件不存在: {path}")
        return {"uname": "", "title": "", "bv_id": "", "uid": "", "crawl_time": ""}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "uname": data.get("uname", data.get("name", "")),
        "title": data.get("title", ""),
        "bv_id": data.get("bv_id", ""),
        "uid": data.get("uid", ""),
        "crawl_time": data.get("crawl_time", ""),
    }


def _parse_timestamp(value) -> datetime | None:
    """将 Unix 时间戳转为 datetime，兼容毫秒级"""
    if not value:
        return None
    try:
        ts = int(value)
        if ts > 1e10:      # 毫秒
            ts = ts / 1000
        return datetime.fromtimestamp(ts)
    except Exception:
        return None
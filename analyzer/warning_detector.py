"""
analyzer/warning_detector.py
舆情预警检测

修改时间：
    2026-06-27
-----------------------------
路径结构调整：
    - 历史文件路径与 video_stats 对齐: data/analysis/{uname}/{title}/{bv_id}/history.json
    - 预警结果带时间目录: data/analysis/{uname}/{title}/{bv_id}/{time_str}/warnings.json
    save_warnings 新增可选参数 time_str。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import config.config as cfg
from utils.log_utils import get_logger, log_event

logger = get_logger()


def _bv_dir(uname: str, title: str, bv_id: str) -> Path:
    d = Path(cfg.ANALYSIS_DIR) / uname / title / bv_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _history_path(uname: str, title: str, bv_id: str) -> Path:
    return _bv_dir(uname, title, bv_id) / cfg.HISTORY_FILENAME_SUFFIX


def record_sentiment_summary(bv_id: str, video_info: list, summary: dict) -> bool:
    uname, title = video_info[1], video_info[2]
    path = _history_path(uname, title, bv_id)

    if not path.exists():
        logger.warning(f"[warning] 还没有历史记录，无法写入情绪摘要: {path}")
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        logger.warning(f"[warning] 历史文件损坏，无法写入情绪摘要: {path}")
        return False

    records = history.get("records", [])
    if not records:
        logger.warning("[warning] 历史记录为空，无法写入情绪摘要")
        return False

    records[-1]["sentiment_summary"] = summary
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    logger.debug(f"[warning] 已写入情绪摘要到最新记录: {summary}")
    log_event("sentiment_summary_recorded", bv_id=bv_id, summary=summary)
    return True


def _neg_ratio(summary: dict | None) -> float | None:
    if not summary:
        return None
    total = sum(int(v) for v in summary.values())
    if total == 0:
        return None
    return int(summary.get("负向", 0)) / total


def detect_warnings(history: dict) -> list[dict]:
    records = history.get("records", [])
    warnings: list[dict] = []
    if not records:
        return warnings

    latest = records[-1]
    prev = records[-2] if len(records) >= 2 else None
    latest_time = latest.get("crawl_time", "")
    latest_stat = latest.get("stat", {})
    latest_neg = _neg_ratio(latest.get("sentiment_summary"))

    if latest_neg is not None and latest_neg >= cfg.WARNING_NEG_RATIO_THRESHOLD:
        warnings.append({
            "type": "neg_ratio_high", "level": "warning",
            "message": f"负向评论占比达到 {latest_neg:.0%}，超过预警线 "
                       f"{cfg.WARNING_NEG_RATIO_THRESHOLD:.0%}",
            "at": latest_time, "value": round(latest_neg, 4),
        })

    if prev is not None:
        prev_neg = _neg_ratio(prev.get("sentiment_summary"))
        prev_stat = prev.get("stat", {})
        if latest_neg is not None and prev_neg is not None:
            jump = latest_neg - prev_neg
            if jump >= cfg.WARNING_NEG_RATIO_JUMP:
                warnings.append({
                    "type": "neg_ratio_jump", "level": "warning",
                    "message": f"负向评论占比从 {prev_neg:.0%} 升到 {latest_neg:.0%}"
                               f"（+{jump:.0%}），出现明显恶化",
                    "at": latest_time, "value": round(jump, 4),
                })
        prev_view = int(prev_stat.get("view", 0) or 0)
        latest_view = int(latest_stat.get("view", 0) or 0)
        if prev_view > 0 and latest_view >= prev_view * cfg.WARNING_VIEW_SPIKE_RATIO:
            ratio = latest_view / prev_view
            warnings.append({
                "type": "view_spike", "level": "info",
                "message": f"播放量从 {prev_view} 涨到 {latest_view}"
                           f"（{ratio:.1f} 倍），可能正在发酵",
                "at": latest_time, "value": round(ratio, 2),
            })
    return warnings


def save_warnings(bv_id: str, video_info: list, warnings: list[dict], time_str: str | None = None) -> str:
    """
    预警结果落盘到 data/analysis/{uname}/{title}/{bv_id}/{time_str}/warnings.json
    time_str 不传则内部生成。
    """
    uname, title = video_info[1], video_info[2]
    now = datetime.now()
    time_str = time_str or now.strftime("%Y%m%d_%H%M%S")

    save_dir = _bv_dir(uname, title, bv_id) / time_str
    save_dir.mkdir(parents=True, exist_ok=True)
    path = save_dir / "warnings.json"

    payload = {
        "bv_id": bv_id, "uname": uname, "title": title,
        "check_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "warning_count": len(warnings),
        "warnings": warnings,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if warnings:
        logger.warning(f"⚠️  检测到 {len(warnings)} 条预警: " +
                       "; ".join(w["message"] for w in warnings))
    else:
        logger.info("✅ 未检测到舆情预警")
    log_event("warnings_saved", bv_id=bv_id, path=str(path), warning_count=len(warnings))
    return str(path)
"""
analyzer/video_stats.py
视频统计数据（播放/弹幕/评论/三连等）的保存、历史累积、趋势图生成

设计：
  - 每个 BV 号在 data/analysis/{uname}/{title}/ 下维护一个
    {bv_id}_history.json，记录这个视频每一次抓取的 stat 快照（追加式，不覆盖）
  - 同时每次抓取也单独落盘一份当次快照
    {bv_id}_{time_str}_stats_analysis.json，方便单次查看/调试
  - 历史记录 >= MIN_POINTS_FOR_TREND 条时，自动生成趋势图 PNG：
    {bv_id}_trend.png

外部只需要调用 save_video_stats() 一个函数。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 无显示环境下也能画图
import matplotlib.pyplot as plt

import config.config as cfg
from utils.log_utils import get_logger, log_event

logger = get_logger()

# 让中文在 matplotlib 里正常显示：扫描系统已安装字体，自动选一个支持中文的
plt.rcParams["axes.unicode_minus"] = False


def _setup_cjk_font():
    import matplotlib.font_manager as fm
    candidates = [
        "Noto Sans CJK SC", "Noto Sans CJK", "Noto Serif CJK SC",
        "PingFang SC", "Microsoft YaHei", "SimHei", "WenQuanYi Zen Hei",
        "Source Han Sans CN", "Droid Sans Fallback",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name]
            return name
    # 退而求其次：扫描字体文件名里带 CJK/CN/SC 的
    for f in fm.fontManager.ttflist:
        if any(k in f.fname for k in ("CJK", "CN", "SC", "noto")):
            plt.rcParams["font.sans-serif"] = [f.name]
            return f.name
    # 找不到中文字体会导致图表里中文显示方块，属于需要终端立即看到的问题
    logger.warning("未找到中文字体，图表中文可能显示为方块")
    return None


_setup_cjk_font()


# ------------------------------------------------------------------ paths --

def _video_dir(uname: str, title: str) -> Path:
    """返回该视频的数据目录，自动创建"""
    d = Path(cfg.ANALYSIS_DIR) / uname / title
    d.mkdir(parents=True, exist_ok=True)
    return d


def _history_path(uname: str, title: str, bv_id: str) -> Path:
    return _video_dir(uname, title) / f"{bv_id}_{cfg.HISTORY_FILENAME_SUFFIX}"


def _trend_image_path(uname: str, title: str, bv_id: str) -> Path:
    return _video_dir(uname, title) / f"{bv_id}_trend.png"


# ------------------------------------------------------------------ core ---

def save_video_stats(bv_id: str, video_info: list, stat: dict) -> dict:
    """
    保存一次视频统计数据快照，并更新历史记录、（在数据足够时）重绘趋势图

    参数:
        bv_id      : 视频 BV 号
        video_info : [UID, uname, title]
        stat       : 视频统计字典，原生 B 站字段，例如
                      {"view": 12345, "danmaku": 100, "reply": 50,
                       "favorite": 30, "coin": 80, "share": 10, "like": 200}
                      允许只传部分字段，缺失字段按 0 处理

    返回:
        {
          "snapshot_path": 本次快照 json 路径,
          "history_path": 历史记录 json 路径,
          "trend_image_path": 趋势图 png 路径（不足以画图时为 None）,
          "point_count": 当前历史记录条数
        }
    """
    uid = video_info[0]
    uname = video_info[1]
    title = video_info[2]

    now = datetime.now()
    time_str = now.strftime("%Y%m%d_%H%M%S")

    # 补全字段，缺失的填 0，避免后续画图 KeyError
    full_stat = {field: int(stat.get(field, 0) or 0) for field in cfg.VIDEO_STAT_FIELDS}

    save_dir = _video_dir(uname, title)

    # ---------- 1. 保存本次快照 ----------
    snapshot = {
        "bv_id": bv_id,
        "uid": uid,
        "uname": uname,
        "title": title,
        "crawl_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "stat": full_stat,
    }
    snapshot_path = save_dir / f"{bv_id}_{time_str}_stats_analysis.json"
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    logger.debug(f"[video_stats] 快照已保存: {snapshot_path}")

    # ---------- 2. 追加进历史记录 ----------
    history_path = _history_path(uname, title, bv_id)
    history = _load_history(history_path)
    history["bv_id"] = bv_id
    history["uid"] = uid
    history["uname"] = uname
    history["title"] = title
    history.setdefault("records", [])
    history["records"].append({
        "crawl_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": now.timestamp(),
        "stat": full_stat,
    })
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    logger.debug(f"[video_stats] 历史记录已更新: {history_path} (共 {len(history['records'])} 条)")

    log_event(
        "video_stats_snapshot_saved",
        bv_id=bv_id,
        snapshot_path=str(snapshot_path),
        history_path=str(history_path),
        point_count=len(history["records"]),
        stat=full_stat,
    )

    # ---------- 3. 数据足够时重绘趋势图 ----------
    trend_path = None
    if len(history["records"]) >= cfg.MIN_POINTS_FOR_TREND:
        trend_path = plot_trend(history, uname, title, bv_id)

    return {
        "snapshot_path": str(snapshot_path),
        "history_path": str(history_path),
        "trend_image_path": str(trend_path) if trend_path else None,
        "point_count": len(history["records"]),
    }


def _load_history(history_path: Path) -> dict:
    if history_path.exists():
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # 历史文件损坏会导致历史数据丢失，属于需要终端立即看到的问题
            logger.warning(f"[video_stats] 历史文件损坏，重新创建: {history_path}")
            log_event("history_file_corrupted", path=str(history_path))
    return {}


# ------------------------------------------------------------------ plot ---

def plot_trend(history: dict, uname: str, title: str, bv_id: str) -> Path:
    """
    根据历史记录绘制趋势图（PNG），包含两个子图：
      1. 播放量 / 弹幕数 / 评论数
      2. 三连数据：点赞 / 投币 / 收藏 (+ 分享)
    返回图片路径
    """
    records = history.get("records", [])
    times = [r["crawl_time"] for r in records]
    x = list(range(len(records)))

    fig, axes = plt.subplots(2, 1, figsize=cfg.TREND_FIG_SIZE, sharex=True)

    # ---- 子图 1：播放/弹幕/评论 ----
    ax1 = axes[0]
    for field, color in [("view", "#5b9bd5"), ("danmaku", "#ed7d31"), ("reply", "#70ad47")]:
        ys = [r["stat"].get(field, 0) for r in records]
        ax1.plot(x, ys, marker="o", label=cfg.VIDEO_STAT_FIELDS.get(field, field), color=color)
    ax1.set_ylabel("数量")
    ax1.set_title(f"{title}  ({bv_id})  数据趋势")
    ax1.legend(loc="upper left")
    ax1.grid(alpha=0.3)

    # ---- 子图 2：三连 + 分享 ----
    ax2 = axes[1]
    colors2 = {"like": "#f08080", "coin": "#d8b365", "favorite": "#5ab4ac", "share": "#9b7fc7"}
    for field in cfg.SANLIAN_FIELDS + ["share"]:
        ys = [r["stat"].get(field, 0) for r in records]
        ax2.plot(x, ys, marker="o", label=cfg.VIDEO_STAT_FIELDS.get(field, field),
                  color=colors2.get(field))
    ax2.set_ylabel("数量")
    ax2.set_xlabel("抓取批次")
    ax2.legend(loc="upper left")
    ax2.grid(alpha=0.3)

    # x 轴用抓取时间作为刻度标签（旋转避免重叠）
    ax2.set_xticks(x)
    ax2.set_xticklabels(times, rotation=30, ha="right", fontsize=8)

    fig.tight_layout()

    out_path = _trend_image_path(uname, title, bv_id)
    fig.savefig(out_path, dpi=cfg.TREND_FIG_DPI)
    plt.close(fig)
    logger.info(f"📈 趋势图已保存: {out_path}")
    log_event("trend_plot_saved", bv_id=bv_id, path=str(out_path), point_count=len(records))
    return out_path


# ------------------------------------------------------------------ misc ---

def get_history(bv_id: str, video_info: list) -> dict:
    """读取某个视频目前累积的历史记录（外部查询用）"""
    uname, title = video_info[1], video_info[2]
    path = _history_path(uname, title, bv_id)
    return _load_history(path)
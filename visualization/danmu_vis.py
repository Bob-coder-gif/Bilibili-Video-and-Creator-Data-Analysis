"""
danmu_vis.py


修改时间：
    2026-06-10
----------------------------------
功能：
    弹幕可视化

    1. plot_top_danmu     —— 高频弹幕词条柱状图（对标 plot_top_comments）
    2. plot_danmu_density —— 弹幕时间轴密度分布图
    3. plot_danmu_wordcloud —— 弹幕词云图

技术：
    - matplotlib
    - wordcloud
    - jieba（中文分词，用于词云）
===============================

输入数据格式（来自 fetch_danmu.fetch_danmu）：
    list[dict]，每个 dict 包含：
        "time"      : float  —— 弹幕出现时间（秒）
        "type"      : int    —— 弹幕类型（1=滚动, 4=底部, 5=顶部 ...）
        "size"      : int    —— 字号
        "color"     : int    —— 颜色（十进制）
        "timestamp" : int    —— 发送时间（Unix 时间戳）
        "text"      : str    —— 弹幕内容
===============================

修改时间：
    2026-06-21
----------------------------------
修改内容：
    1. 去掉所有 plt.show()（非交互后端下只会触发 UserWarning，没有实际作用）
    2. "图片已保存" 改为 logger.debug
    3. "弹幕列表为空"等跳过情况改为 logger.warning（终端要看到，否则会以为图生成了）
===============================

修改时间：
    2026-06-27
----------------------------------
修改内容：
    图片保存路径改为 data/processed/danmu/{uname}/{title}/{bv_id}/{time_str}/xxx.png
    （bv_id 和时间作为目录层级，与项目其它产物路径风格统一）。
    三个画图函数新增可选参数 time_str：由 crawler_pipeline 传入本次任务统一的
    时间目录名，保证与同一次任务的其它产物落在同一个 {time_str}/ 目录；不传则内部生成。
    注意：本文件里另有一个 _time_str(seconds) 函数，那是把"秒数"格式化成 mm:ss 用于
    时间轴刻度的，与这里的 time_str 时间目录名是两回事，互不影响。
===============================

"""

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from datetime import datetime
from pathlib import Path
from collections import Counter
from utils.log_utils import get_logger, log_event

logger = get_logger()

# 词云 & 分词（可选依赖）
try:
    from wordcloud import WordCloud
    import jieba
    _WORDCLOUD_AVAILABLE = True
except ImportError:
    _WORDCLOUD_AVAILABLE = False


# ── 中文支持 ──────────────────────────────────────────────
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


# ── 工具函数 ──────────────────────────────────────────────
def _make_save_dir(bv_id: str, video_info: tuple, time_str: str) -> Path:
    """
    根据 video_info / bv_id / time_str 构造保存目录（与 comment_vis.py 保持一致）

    video_info[0] = UID
    video_info[1] = uname
    video_info[2] = title

    路径: data/processed/danmu/{uname}/{title}/{bv_id}/{time_str}/
    """
    uname = video_info[1]
    title = video_info[2]
    save_dir = Path(f"data/processed/danmu/{uname}/{title}/{bv_id}/{time_str}")
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir


def _fmt_time(seconds: float) -> str:
    """将秒数格式化为 mm:ss，用于时间轴刻度"""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


# 兼容旧名称：原文件里这个函数叫 _time_str，保留别名以防别处引用
_time_str = _fmt_time


# ── 1. 高频弹幕词条柱状图 ──────────────────────────────────
def plot_top_danmu(top_danmu: list[tuple], bv_id: str, video_info: tuple,
                   time_str: str | None = None):
    """
    绘制高频弹幕词条水平柱状图。

    参数：
        top_danmu  : [(弹幕文本, 出现次数), ...]，按次数降序排列
        bv_id      : 视频BV号
        video_info : (UID, uname, title)
        time_str   : 本次任务统一的时间目录名；不传则内部生成
    """
    texts  = [x[0] for x in top_danmu]
    counts = [x[1] for x in top_danmu]

    plt.figure(figsize=(10, 5))
    plt.barh(texts, counts, color="#23ADE5")  # B站蓝
    plt.xlabel("出现次数")
    plt.title(f"{bv_id} 高频弹幕词条")

    plt.gca().invert_yaxis()
    plt.tight_layout()

    time_str  = time_str or datetime.now().strftime("%Y%m%d_%H%M%S")
    save_dir  = _make_save_dir(bv_id, video_info, time_str)
    save_path = save_dir / "top_danmu.png"

    plt.savefig(save_path, dpi=150)
    plt.close()

    logger.debug(f"图片已保存: {save_path}")
    log_event("top_danmu_plot_saved", bv_id=bv_id, path=str(save_path))


# ── 2. 弹幕时间轴密度分布图 ───────────────────────────────
def plot_danmu_density(
    danmus: list[dict],
    bv_id: str,
    video_info: tuple,
    bin_seconds: int = 30,
    time_str: str | None = None,
):
    """
    绘制弹幕随视频进度的密度折线图。

    参数：
        danmus      : fetch_danmu 返回的弹幕列表
        bv_id       : 视频BV号
        video_info  : (UID, uname, title)
        bin_seconds : 每个时间段的长度（秒），默认 30 秒一格
        time_str    : 本次任务统一的时间目录名；不传则内部生成
    """
    if not danmus:
        logger.warning("弹幕列表为空，跳过密度图绘制")
        return

    times = [d["time"] for d in danmus]
    max_time = max(times)

    # 按 bin_seconds 分桶统计
    bins = np.arange(0, max_time + bin_seconds, bin_seconds)
    counts, edges = np.histogram(times, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2  # 每个桶的中点（秒）

    fig, ax = plt.subplots(figsize=(12, 4))

    ax.fill_between(centers, counts, alpha=0.25, color="#23ADE5")
    ax.plot(centers, counts, color="#23ADE5", linewidth=1.5)

    ax.set_xlabel("视频进度")
    ax.set_ylabel(f"弹幕数量 / {bin_seconds}s")
    ax.set_title(f"{bv_id} 弹幕时间轴密度分布")

    # X 轴刻度转为 mm:ss
    ax.xaxis.set_major_formatter(
        ticker.FuncFormatter(lambda x, _: _fmt_time(x))
    )
    plt.xticks(rotation=45)
    plt.tight_layout()

    time_str  = time_str or datetime.now().strftime("%Y%m%d_%H%M%S")
    save_dir  = _make_save_dir(bv_id, video_info, time_str)
    save_path = save_dir / "danmu_density.png"

    plt.savefig(save_path, dpi=150)
    plt.close(fig)

    logger.debug(f"图片已保存: {save_path}")
    log_event("danmu_density_plot_saved", bv_id=bv_id, path=str(save_path))


# ── 3. 弹幕词云图 ─────────────────────────────────────────
def plot_danmu_wordcloud(
    danmus: list[dict],
    bv_id: str,
    video_info: tuple,
    font_path: str = "simhei.ttf",
    time_str: str | None = None,
):
    """
    绘制弹幕词云图（需要安装 wordcloud 和 jieba）。

    参数：
        danmus     : fetch_danmu 返回的弹幕列表
        bv_id      : 视频BV号
        video_info : (UID, uname, title)
        font_path  : 中文字体路径，默认 simhei.ttf
        time_str   : 本次任务统一的时间目录名；不传则内部生成
    """
    if not _WORDCLOUD_AVAILABLE:
        logger.warning("词云功能需要安装依赖：pip install wordcloud jieba")
        return

    if not danmus:
        logger.warning("弹幕列表为空，跳过词云绘制")
        return

    # 拼接所有弹幕文本，jieba 分词
    all_text = " ".join(d["text"] for d in danmus if d.get("text"))
    seg_text = " ".join(jieba.cut(all_text))

    wc = WordCloud(
        font_path=font_path,
        width=900,
        height=500,
        background_color="white",
        colormap="Blues",
        max_words=150,
        collocations=False,   # 避免重复词组
    ).generate(seg_text)

    plt.figure(figsize=(12, 6))
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    plt.title(f"{bv_id} 弹幕词云")
    plt.tight_layout()

    time_str  = time_str or datetime.now().strftime("%Y%m%d_%H%M%S")
    save_dir  = _make_save_dir(bv_id, video_info, time_str)
    save_path = save_dir / "danmu_wordcloud.png"

    plt.savefig(save_path, dpi=150)
    plt.close()

    logger.debug(f"图片已保存: {save_path}")
    log_event("danmu_wordcloud_plot_saved", bv_id=bv_id, path=str(save_path))
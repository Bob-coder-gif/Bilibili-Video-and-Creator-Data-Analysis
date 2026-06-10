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

"""

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from datetime import datetime
from pathlib import Path
from collections import Counter

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
def _make_save_dir(bv_id: str, video_info: tuple) -> Path:
    """
    根据 video_info 构造保存目录（与 comment_vis.py 保持一致）

    video_info[0] = UID
    video_info[1] = uname
    video_info[2] = title
    """
    uname = video_info[1]
    title = video_info[2]
    save_dir = Path(f"data/processed/danmu/{uname}/{title}")
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir


def _time_str(seconds: float) -> str:
    """将秒数格式化为 mm:ss，用于时间轴刻度"""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


# ── 1. 高频弹幕词条柱状图 ──────────────────────────────────
def plot_top_danmu(top_danmu: list[tuple], bv_id: str, video_info: tuple):
    """
    绘制高频弹幕词条水平柱状图。

    参数：
        top_danmu  : [(弹幕文本, 出现次数), ...]，按次数降序排列
        bv_id      : 视频BV号
        video_info : (UID, uname, title)
    """
    texts  = [x[0] for x in top_danmu]
    counts = [x[1] for x in top_danmu]

    plt.figure(figsize=(10, 5))
    plt.barh(texts, counts, color="#23ADE5")  # B站蓝
    plt.xlabel("出现次数")
    plt.title(f"{bv_id} 高频弹幕词条")

    plt.gca().invert_yaxis()
    plt.tight_layout()

    save_dir  = _make_save_dir(bv_id, video_info)
    time_str  = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = save_dir / f"{bv_id}_{time_str}_top_danmu.png"

    plt.savefig(save_path, dpi=150)
    print(f"图片已保存: {save_path}")
    plt.show()


# ── 2. 弹幕时间轴密度分布图 ───────────────────────────────
def plot_danmu_density(
    danmus: list[dict],
    bv_id: str,
    video_info: tuple,
    bin_seconds: int = 30,
):
    """
    绘制弹幕随视频进度的密度折线图。

    参数：
        danmus      : fetch_danmu 返回的弹幕列表
        bv_id       : 视频BV号
        video_info  : (UID, uname, title)
        bin_seconds : 每个时间段的长度（秒），默认 30 秒一格
    """
    if not danmus:
        print("[警告] 弹幕列表为空，跳过密度图绘制")
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
        ticker.FuncFormatter(lambda x, _: _time_str(x))
    )
    plt.xticks(rotation=45)
    plt.tight_layout()

    save_dir  = _make_save_dir(bv_id, video_info)
    time_str  = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = save_dir / f"{bv_id}_{time_str}_danmu_density.png"

    plt.savefig(save_path, dpi=150)
    print(f"图片已保存: {save_path}")
    plt.show()


# ── 3. 弹幕词云图 ─────────────────────────────────────────
def plot_danmu_wordcloud(
    danmus: list[dict],
    bv_id: str,
    video_info: tuple,
    font_path: str = "simhei.ttf",
):
    """
    绘制弹幕词云图（需要安装 wordcloud 和 jieba）。

    参数：
        danmus     : fetch_danmu 返回的弹幕列表
        bv_id      : 视频BV号
        video_info : (UID, uname, title)
        font_path  : 中文字体路径，默认 simhei.ttf
                     如果系统字体路径不同请手动传入，例如：
                     "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
    """
    if not _WORDCLOUD_AVAILABLE:
        print("[错误] 词云功能需要安装依赖：pip install wordcloud jieba")
        return

    if not danmus:
        print("[警告] 弹幕列表为空，跳过词云绘制")
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

    save_dir  = _make_save_dir(bv_id, video_info)
    time_str  = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = save_dir / f"{bv_id}_{time_str}_danmu_wordcloud.png"

    plt.savefig(save_path, dpi=150)
    print(f"图片已保存: {save_path}")
    plt.show()
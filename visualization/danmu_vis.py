"""
visualization/danmu_vis.py
弹幕可视化

    1. plot_top_danmu       —— 高频弹幕词条柱状图
    2. plot_danmu_density   —— 弹幕时间轴密度分布图
    3. plot_danmu_wordcloud —— 弹幕词云图

输入数据（来自 fetch_danmu.fetch_danmu）：list[dict]，每项含
    time(float, 出现时间秒) / type / size / color / timestamp / text

保存路径：data/processed/danmu/{uname}/{title}/{bv_id}/{time_str}/xxx.png

修改时间：
    2026-06-10  初版
    2026-06-21  去掉 plt.show()；日志分级
    2026-06-27  保存路径改为 bv_id / time_str 目录层级，新增 time_str 参数

修改时间：
    2026-09-28
----------------------------------
    1. 字体不再写死 SimHei / "simhei.ttf"，改为 utils.plot_utils 自动查找
       （非 Windows 系统原来会方块字，词云直接报错）；同时保证使用 Agg 后端。
    2. 词云加入停用词（与关键词提取共用），避免"哈哈哈""233"占满画面。
    3. 弹幕全是表情/标点时 WordCloud 会抛 ValueError 让整个任务失败，现在跳过。
    4. 删除 _time_str 兼容别名（没有任何地方引用）。

修改时间：
    2026-09-28（第二次）
----------------------------------
    1. 词云过滤掉不含文字的词：原来 "____"、"一一" 这类用户拿来当分隔线的符号
       会通过"长度 > 1"的过滤，在词云里显示成一条条横线。
    2. 词云改为只按空格切词，保留 jieba 的分词结果，不让 WordCloud 再按自己的规则切一遍。
    3. 高频弹幕柱状图的标签截断到 _MAX_LABEL_LEN 个字：长弹幕会把左边距撑爆，
       触发 "Tight layout not applied" 警告，图也会被挤变形。
"""

import re
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

import config.config as cfg
from utils.file_utils import video_dir
from utils.log_utils import get_logger, log_event
from utils.plot_utils import CJK_FONT_PATH

logger = get_logger()

# 词云 & 分词（可选依赖）
try:
    from wordcloud import WordCloud
    import jieba
    _WORDCLOUD_AVAILABLE = True
except ImportError:
    _WORDCLOUD_AVAILABLE = False

_BILI_BLUE = "#23ADE5"
_MAX_LABEL_LEN = 18   # 柱状图标签最长字数

# 至少含一个汉字 / 字母 / 数字才算"词"
_HAS_TEXT = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
# 只由"一"、下划线、空白组成的串，是用户画的分隔线，不是词
_SEPARATOR = re.compile(r"[一_\s]+")


def _is_word(w: str, stopwords) -> bool:
    w = w.strip()
    return (
        len(w) > 1
        and w not in stopwords
        and _HAS_TEXT.search(w) is not None
        and _SEPARATOR.fullmatch(w) is None
    )


def _short(text: str) -> str:
    return text if len(text) <= _MAX_LABEL_LEN else text[:_MAX_LABEL_LEN] + "…"


def _save_path(bv_id: str, video_info: list, time_str: str | None, filename: str):
    time_str = time_str or datetime.now().strftime("%Y%m%d_%H%M%S")
    return video_dir(cfg.PROCESSED_DANMU_DIR, video_info, bv_id, time_str) / filename


def _fmt_time(seconds: float) -> str:
    """秒数 -> mm:ss，用于时间轴刻度"""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


# ── 1. 高频弹幕词条柱状图 ──────────────────────────────────
def plot_top_danmu(top_danmu: list[tuple], bv_id: str, video_info: list,
                   time_str: str | None = None):
    """top_danmu: [(弹幕文本, 出现次数), ...]，按次数降序"""
    if not top_danmu:
        logger.warning("没有高频弹幕数据，跳过柱状图绘制")
        return

    texts = [_short(x[0]) for x in top_danmu]
    counts = [x[1] for x in top_danmu]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(texts, counts, color=_BILI_BLUE)
    ax.set_xlabel("出现次数")
    ax.set_title(f"{bv_id} 高频弹幕词条")
    ax.invert_yaxis()
    fig.tight_layout()

    path = _save_path(bv_id, video_info, time_str, "top_danmu.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    logger.debug(f"图片已保存: {path}")
    log_event("top_danmu_plot_saved", bv_id=bv_id, path=str(path))


# ── 2. 弹幕时间轴密度分布图 ───────────────────────────────
def plot_danmu_density(danmus: list[dict], bv_id: str, video_info: list,
                       bin_seconds: int = 30, time_str: str | None = None):
    """按 bin_seconds 分桶统计弹幕随视频进度的数量"""
    if not danmus:
        logger.warning("弹幕列表为空，跳过密度图绘制")
        return

    times = [d["time"] for d in danmus]
    bins = np.arange(0, max(times) + bin_seconds, bin_seconds)
    counts, edges = np.histogram(times, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(centers, counts, alpha=0.25, color=_BILI_BLUE)
    ax.plot(centers, counts, color=_BILI_BLUE, linewidth=1.5)
    ax.set_xlabel("视频进度")
    ax.set_ylabel(f"弹幕数量 / {bin_seconds}s")
    ax.set_title(f"{bv_id} 弹幕时间轴密度分布")
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: _fmt_time(x)))
    plt.setp(ax.get_xticklabels(), rotation=45)
    fig.tight_layout()

    path = _save_path(bv_id, video_info, time_str, "danmu_density.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    logger.debug(f"图片已保存: {path}")
    log_event("danmu_density_plot_saved", bv_id=bv_id, path=str(path))


# ── 3. 弹幕词云图 ─────────────────────────────────────────
def plot_danmu_wordcloud(danmus: list[dict], bv_id: str, video_info: list,
                         time_str: str | None = None):
    """jieba 分词后生成词云（需要 wordcloud + jieba + 系统中文字体）"""
    if not _WORDCLOUD_AVAILABLE:
        logger.warning("词云功能需要安装依赖：pip install wordcloud jieba")
        return
    if not CJK_FONT_PATH:
        logger.warning("系统中没有可用的中文字体，跳过词云绘制")
        return
    if not danmus:
        logger.warning("弹幕列表为空，跳过词云绘制")
        return

    # 延迟 import：analyzer 层 import 了 jieba.analyse，放顶部会拖慢启动
    from analyzer.keyword_extractor import load_stopwords
    stopwords = load_stopwords(cfg.STOPWORDS_FILE)

    all_text = " ".join(d["text"] for d in danmus if d.get("text"))
    words = [w.strip() for w in jieba.cut(all_text) if _is_word(w, stopwords)]
    if not words:
        logger.warning("弹幕分词后没有有效词语，跳过词云绘制")
        return

    try:
        wc = WordCloud(
            font_path=CJK_FONT_PATH,
            width=900, height=500,
            background_color="white",
            colormap="Blues",
            max_words=150,
            collocations=False,
            regexp=r"\S+",   # 按空格切，保留 jieba 的分词结果
        ).generate(" ".join(words))
    except ValueError as e:
        logger.warning(f"词云生成失败，跳过: {e}")
        return

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    ax.set_title(f"{bv_id} 弹幕词云")
    fig.tight_layout()

    path = _save_path(bv_id, video_info, time_str, "danmu_wordcloud.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    logger.debug(f"图片已保存: {path}")
    log_event("danmu_wordcloud_plot_saved", bv_id=bv_id, path=str(path))
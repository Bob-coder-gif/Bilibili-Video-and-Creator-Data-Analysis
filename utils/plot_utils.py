"""
utils/plot_utils.py
matplotlib 公共设置：非交互后端 + 自动查找中文字体

2026-09-28 新增：
    原来 video_stats.py 有一套自动找中文字体的逻辑，而 danmu_vis.py 写死了 SimHei，
    词云写死了 "simhei.ttf"——换到没有黑体的系统（Linux / macOS）就会出现方块字或
    直接报错。而且 danmu_vis 没有设置 Agg 后端，能在后台线程里画图只是因为
    video_stats 恰好在同一时刻被 import。现在两个文件统一从这里取。

    同时屏蔽"Glyph xxx missing from font"警告：弹幕里常有爪哇文装饰符 ꧁꧂ 等
    冷门字符，任何中文字体都没有，只会显示成方块，警告对我们没有意义。
"""

import warnings

import matplotlib
matplotlib.use("Agg")   # 后台线程画图必须用非交互后端，必须在 import pyplot 之前设置

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

from utils.log_utils import get_logger

logger = get_logger()

_CANDIDATES = [
    "Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC", "Noto Sans CJK",
    "Source Han Sans CN", "WenQuanYi Zen Hei", "Droid Sans Fallback",
]


def _find_cjk_font():
    """返回 (字体名, 字体文件路径)，找不到返回 (None, None)"""
    by_name = {f.name: f.fname for f in fm.fontManager.ttflist}
    for name in _CANDIDATES:
        if name in by_name:
            return name, by_name[name]
    for f in fm.fontManager.ttflist:
        if any(k in f.fname for k in ("CJK", "cjk", "SC", "Hei", "hei", "YaHei")):
            return f.name, f.fname
    return None, None


CJK_FONT_NAME, CJK_FONT_PATH = _find_cjk_font()

if CJK_FONT_NAME:
    plt.rcParams["font.sans-serif"] = [CJK_FONT_NAME]
else:
    logger.warning("未找到中文字体，图表中文可能显示为方块，词云将无法生成")
plt.rcParams["axes.unicode_minus"] = False

warnings.filterwarnings("ignore", message=r"Glyph \d+ .* missing from font")
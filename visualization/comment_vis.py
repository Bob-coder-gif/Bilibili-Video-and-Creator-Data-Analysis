"""
comment_vis.py


修改时间：
    2026-04-06
----------------------------------
功能：
    评论频率可视化

技术：
    - matplotlib
===============================

修改时间：
    2026-04-21
----------------------------------
修改内容：
    1. 优化了图片保存路径的生成逻辑，确保路径的唯一性和可读性
===============================

修改时间：
    2026-06-10
----------------------------------
修改内容：
    1. 修复了 plt.savefig() 缺失的问题（图表之前只展示、未实际写入磁盘）
    2. 添加 tight_layout()，防止长文本标签被截断
    3. 统一配色为 B站蓝 #23ADE5（与 danmu_vis.py 保持一致）
    4. 添加函数类型注解（与项目其他文件风格保持一致）
===============================

"""

import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path


# 中文支持
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


def plot_top_comments(top_comments: list[tuple], bv_id: str, video_info: tuple):
    """
    绘制高频评论水平柱状图。

    参数：
        top_comments : [(评论文本, 出现次数), ...]，按次数降序排列
        bv_id        : 视频BV号
        video_info   : (UID, uname, title)
    """
    texts  = [x[0] for x in top_comments]
    counts = [x[1] for x in top_comments]

    plt.figure(figsize=(10, 5))
    plt.barh(texts, counts, color="#23ADE5")  # B站蓝
    plt.xlabel("数量")
    plt.title(f"{bv_id} 高频评论")

    plt.gca().invert_yaxis()
    plt.tight_layout()

    uname = video_info[1]
    title = video_info[2]

    # 时间戳
    time_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 确保目录存在
    save_dir = Path(f"data/processed/comments/{uname}/{title}")
    save_dir.mkdir(parents=True, exist_ok=True)

    # 保存图片
    save_path = save_dir / f"{bv_id}_{time_str}_top_comments.png"
    plt.savefig(save_path, dpi=150)

    print(f"图片已保存: {save_path}")

    plt.show()
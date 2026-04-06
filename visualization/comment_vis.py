"""
comment_vis.py

功能：
    评论频率可视化

技术：
    - matplotlib

修改时间：
    2026-04-06
"""


import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path


# 中文支持
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


def plot_top_comments(top_comments, bv_id):
    texts = [x[0] for x in top_comments]
    counts = [x[1] for x in top_comments]

    plt.figure(figsize=(10, 5))
    plt.barh(texts, counts)
    plt.xlabel("数量")
    plt.title(f"{bv_id} 高频评论")

    plt.gca().invert_yaxis()

    # ⭐ 时间戳
    time_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ⭐ 确保目录存在
    save_dir = Path("data/processed")
    save_dir.mkdir(parents=True, exist_ok=True)

    # ⭐ 保存图片（你问的那一行就在这里）
    save_path = save_dir / f"{bv_id}_{time_str}_top_comments.png"
    plt.savefig(save_path, dpi=300, bbox_inches='tight')

    print(f"图片已保存: {save_path}")

    plt.show()
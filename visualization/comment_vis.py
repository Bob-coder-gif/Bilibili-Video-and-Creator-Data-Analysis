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

"""


import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path


# 中文支持
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


def plot_top_comments(top_comments, bv_id,video_info):
    '''
    video_info[0] = UID
    video_info[1] = uname  
    video_info[2] = title
    '''
  
    texts = [x[0] for x in top_comments]
    counts = [x[1] for x in top_comments]

    plt.figure(figsize=(10, 5))
    plt.barh(texts, counts)
    plt.xlabel("数量")
    plt.title(f"{bv_id} 高频评论")

    plt.gca().invert_yaxis()

    uname = video_info[1]
    title = video_info[2]

    # 时间戳
    time_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 确保目录存在
    save_dir = Path(f"data/processed/{uname}/{title}")
    save_dir.mkdir(parents=True, exist_ok=True)

    # 保存图片
    save_path = save_dir / f"{bv_id}_{time_str}_top_comments.png"

    print(f"图片已保存: {save_path}")
    plt.close()  

    plt.show()
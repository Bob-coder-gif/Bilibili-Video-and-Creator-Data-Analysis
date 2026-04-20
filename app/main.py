"""
主程序入口

-----------------
修改时间：
    2026-04-06
新增:
    情绪分析测试
------------------


"""
from crawler.fetch_comments import fetch_comments
from features.comment_analysis import top_repeated_comments
from visualization.comment_vis import plot_top_comments
from utils.file_utils import save_comments
import requests


def get_video_info(bv_id):
    """
    获取UP主UID
    """
    url = "https://api.bilibili.com/x/web-interface/view"
    params = {"bvid": bv_id}

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.bilibili.com/"
    }

    data = requests.get(url, params=params, headers=headers).json()
    return data["data"]["owner"]["mid"]


if __name__ == "__main__":
    #饼叔巴尔干
    #bv_id = "BV1uPDTBhEHX"

    #测试视频1
    bv_id = "BV15edfB8EK1"

    #测试视频2
    bv_id = "BV1kZ4y147Fi"

    print("开始抓取评论...")

    comments = fetch_comments(bv_id, max_count=0)

    # ⭐ 获取UP主UID
    uid = get_video_info(bv_id)

    # ⭐ 保存JSON（带时间版本）
    save_comments(bv_id, uid, comments)

    print("开始统计高频评论...")

    top_comments = top_repeated_comments(comments, top_n=10)

    print("重复评论 TOP10:")
    for text, count in top_comments:
        print(text, count)

    # ⭐ 可视化（你之前写的）
    plot_top_comments(top_comments, bv_id)
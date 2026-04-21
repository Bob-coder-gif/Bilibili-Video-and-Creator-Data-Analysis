"""
主程序入口

修改时间：
    2026-04-06
----------------------------------
新增:
    情绪分析测试
===============================

修改时间：
    2026-04-21
----------------------------------
修改内容：
    1. 增加了获取视频信息的功能（get_video_info函数），获取UP主UID、用户名和视频标题，以保证保存的文件有清晰正确的路径
        测试用例正确通过，已验证功能正常

===============================        
        
"""
from crawler.fetch_comments import fetch_comments
from features.comment_analysis import top_repeated_comments
from visualization.comment_vis import plot_top_comments
from utils.file_utils import save_comments
import requests


def get_video_info(bv_id) -> list[str]:
    """
    获取UP主UID,uname,title等信息
    
    video_info[0] = UID
    video_info[1] = uname  
    video_info[2] = title
    """
    result = []

    url = "https://api.bilibili.com/x/web-interface/view"
    params = {"bvid": bv_id}

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.bilibili.com/"
    }

    data = requests.get(url, params=params, headers=headers).json()

    UID = data["data"]["owner"]["mid"]
    uname = data["data"]["owner"]["name"]
    title = data["data"]["title"]

    result.append(UID)
    result.append(uname)
    result.append(title)

    return result

if __name__ == "__main__":
    #饼叔巴尔干
    #bv_id = "BV1uPDTBhEHX"

    #测试视频1  央视新闻
    bv_id = "BV15edfB8EK1"

    #测试视频2  死水bug
    #bv_id = "BV1kZ4y147Fi"

    #测试视频3  纲手
    #bv_id = "BV1834y1D7L8"

    print("开始抓取评论...")

    comments = fetch_comments(bv_id, max_count=0)

    #  获取video的信息
    video_info = get_video_info(bv_id)

    #  保存JSON（带时间版本）
    save_comments(bv_id, video_info, comments)

    print("开始统计高频评论...")

    top_comments = top_repeated_comments(comments, top_n=10)

    print("重复评论 TOP10:")
    for text, count in top_comments:
        print(text, count)

    #  可视化（你之前写的）
    plot_top_comments(top_comments, bv_id,video_info)
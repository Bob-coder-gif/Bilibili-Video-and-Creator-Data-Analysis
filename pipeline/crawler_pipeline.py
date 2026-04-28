"""
crawler_pipeline.py

爬虫管道
"""

from crawler.fetch_comments import fetch_comments
from utils.file_utils import save_comments, save_danmu
from crawler.get_info_from_browser import get_video_info
from features.comment_analysis import top_repeated_comments
from visualization.comment_vis import plot_top_comments
from crawler.fetch_danmu import fetch_danmu

def crawler_pipeline():
    print("这是爬虫管道的入口文件，主要负责调用各个爬虫模块进行数据抓取。")

    test_bv_id = [
        "BV1uPDTBhEHX",  # 饼叔巴尔干
        "BV15edfB8EK1",  # 央视新闻
        "BV1kZ4y147Fi",  # 死水bug
        "BV1834y1D7L8",  # 纲手
        "BV1LzrSBNEWi",   # 评论回复超过一页
        "BV1zu411R7os"   # 测试弹幕
    ]

    bv_id = test_bv_id[int(input("测试序号（0-5）: "))]

    #爬取并保存评论数据
    comments,video_info = fetch_and_save_comments(bv_id)

    #分析评论并可视化高频评论
    analysis_and_visualization(comments, bv_id,video_info)

    #爬取并保存弹幕数据
    fetch_and_save_danmu(bv_id, video_info)


def fetch_and_save_comments(bv_id):
    print("开始爬取评论...")
    comments = fetch_comments(bv_id, max_count=0)

        #  获取video的信息
    video_info = get_video_info(bv_id)

    #  保存JSON（带时间版本）
    save_comments(bv_id, video_info, comments)

    return comments,video_info



def analysis_and_visualization(comments, bv_id,video_info):

    print("开始统计高频评论...")

    top_comments = top_repeated_comments(comments, top_n=10)

    print("重复评论 TOP10:")
    for text, count in top_comments:
        print(text, count)

    print("开始可视化高频评论...")    
    plot_top_comments(top_comments, bv_id,video_info)


def fetch_and_save_danmu(bv_id, video_info):
    print("开始爬取弹幕...")
    danmus = fetch_danmu(bv_id)
    print(f"弹幕：{danmus}")

    print("开始保存弹幕...")
    save_danmu(bv_id, video_info, danmus)
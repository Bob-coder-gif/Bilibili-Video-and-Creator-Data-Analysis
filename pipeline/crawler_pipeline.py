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
from visualization.danmu_vis import plot_top_danmu, plot_danmu_density, plot_danmu_wordcloud
from collections import Counter


def crawler_pipeline():
    #这是爬虫管道的入口文件，主要负责调用各个爬虫模块进行数据抓取。

    test_bv_id = [
        "BV1uPDTBhEHX",  # 饼叔巴尔干
        "BV15edfB8EK1",  # 央视新闻
        "BV1kZ4y147Fi",  # 死水bug
        "BV1834y1D7L8",  # 纲手
        "BV1LzrSBNEWi",  # 评论回复超过一页
        "BV1zu411R7os",  # 测试弹幕
        "BV1Lvo2BNEZz",  # 何以当归reaction预告
    ]

    bv_id = test_bv_id[int(input("测试序号（0-6）: "))]

    # 爬取并保存评论数据
    comments, video_info = fetch_and_save_comments(bv_id)

    # 分析评论并可视化高频评论
    analysis_and_visualization_comments(comments, bv_id, video_info)

    # 爬取并保存弹幕数据
    danmus = fetch_and_save_danmu(bv_id, video_info)

    # 分析弹幕并可视化
    analysis_and_visualization_danmu(danmus, bv_id, video_info)


def fetch_and_save_comments(bv_id: str) -> tuple:
    print("开始爬取评论...")
    comments = fetch_comments(bv_id, max_count=0)

    # 获取video的信息
    video_info = get_video_info(bv_id)

    # 保存JSON（带时间版本）
    save_comments(bv_id, video_info, comments)

    return comments, video_info


def analysis_and_visualization_comments(comments: dict, bv_id: str, video_info: tuple):
    print("开始统计高频评论...")

    top_comments = top_repeated_comments(comments, top_n=10)

    print("重复评论 TOP10:")
    for text, count in top_comments:
        print(text, count)

    print("开始可视化高频评论...")
    plot_top_comments(top_comments, bv_id, video_info)


def fetch_and_save_danmu(bv_id: str, video_info: tuple) -> list[dict]:
    print("开始爬取弹幕...")
    danmus = fetch_danmu(bv_id)
    print(f"共获取到 {len(danmus)} 条弹幕")

    print("开始保存弹幕...")
    save_danmu(bv_id, video_info, danmus)

    return danmus  # 返回供后续分析使用


def analysis_and_visualization_danmu(danmus: list[dict], bv_id: str, video_info: tuple):
    if not danmus:
        print("[警告] 弹幕列表为空，跳过分析")
        return

    # 统计高频弹幕词条
    print("开始统计高频弹幕...")
    counter = Counter(d["text"] for d in danmus if d.get("text"))
    top_danmu = counter.most_common(10)

    print("高频弹幕 TOP10:")
    for text, count in top_danmu:
        print(text, count)

    # 可视化
    print("开始可视化弹幕...")
    plot_top_danmu(top_danmu, bv_id, video_info)
    plot_danmu_density(danmus, bv_id, video_info)
    plot_danmu_wordcloud(danmus, bv_id, video_info)
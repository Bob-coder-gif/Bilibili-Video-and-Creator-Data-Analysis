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


import pipeline.crawler_pipeline
import pipeline.sentiment_pipeline
import pipeline.pipeline_data_analysis



if __name__ == "__main__":
    bv_id = input("请输入视频 BV 号: ")
    task = pipeline.crawler_pipeline.crawler_pipeline(bv_id)
    task = pipeline.sentiment_pipeline.sentiment_pipeline(task)
    task = pipeline.pipeline_data_analysis.pipeline_data_analysis(task)
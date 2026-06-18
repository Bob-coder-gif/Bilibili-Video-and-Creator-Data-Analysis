import json
from pathlib import Path
from datetime import datetime
import config.config as cfg
import os
import pandas as pd

'''
file_utils.py
功能：
    文件操作工具函数

修改时间：
    2026-04-21
---------------------------------- 
修改内容：
    1.更改了文件保存路径，使其包含UP主用户名和视频标题，确保保存的文件有清晰正确的路径

===============================


修改时间：
    2026-04-28
-----------------------------
修改内容：
    新增了save_danmu函数，用于保存弹幕数据，路径同样包含UP主用户名和视频标题，确保保存的文件有清晰正确的路径

===============================

    '''

def save_profile(profile, bv_id: str):
    """
    保存UP主信息（分类版）
    """

    from pathlib import Path
    import json

    save_dir = Path("data/raw/profile")
    save_dir.mkdir(parents=True, exist_ok=True)

    file_path = save_dir / f"{bv_id}_profile.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)

    print(f"UP主信息已保存: {file_path}")

def load_profile(path: Path):
    from models.video import UploaderProfile
    
    '''
        with open(...) as f
            这种写法会自动管理文件资源，确保在使用完文件后正确关闭它，即使在过程中发生异常也能保证文件被关闭。
            "R"表示读取模式，如果文件不存在会抛出异常。
    '''
    with open(path, "r", encoding="utf-8") as f:
        '''
            json.load()函数从文件中读取JSON数据并将其转换为Python对象。
        '''
        data = json.load(f)

    return UploaderProfile.from_dict(data)

def save_comments(bv_id: str, video_info: list, comments: list):
    """
    保存评论数据（带时间版本）
    video_info[0] = UID
    video_info[1] = uname  
    video_info[2] = title
    """

    from datetime import datetime
    from pathlib import Path
    import json

    now = datetime.now()
    time_str = now.strftime("%Y%m%d_%H%M%S")

    uid = video_info[0]
    uname = video_info[1]
    title = video_info[2]

    data = {
        "name": uname,
        "bv_id": bv_id,
        "uid": uid,
        "uname": uname,
        "title": title,
        "crawl_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "comment_count": len(comments),
        "comments": comments
    }

    save_dir = Path(f"data/raw/comments/{uname}/{title}")
    save_dir.mkdir(parents=True, exist_ok=True)

    #  带时间版本
    file_path = save_dir / f"{bv_id}_{time_str}_comments.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"评论数据已保存: {file_path}")


    # 修bug 新增=========================================   
    cfg.COMMENTS_FILE = f"{cfg.COMMENTS_DIR}/{uname}/{title}/{bv_id}_{time_str}_comments.json"
    
    print(f"更新全局配置: cfg.COMMENTS_FILE = {cfg.COMMENTS_FILE}")
    # ===============================================


def save_danmu(bv_id: str, video_info: list, danmus: list):
    """
    保存弹幕数据
    video_info[0] = UID
    video_info[1] = uname  
    video_info[2] = title
    """

    from datetime import datetime
    from pathlib import Path
    import json

    now = datetime.now()
    time_str = now.strftime("%Y%m%d_%H%M%S")

    uid = video_info[0]
    uname = video_info[1]
    title = video_info[2]

    data = {
        "name": uname,
        "bv_id": bv_id,
        "uid": uid,
        "uname": uname,
        "title": title,
        "crawl_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "danmu_count": len(danmus),
        "danmus": danmus
    }

    save_dir = Path(f"data/raw/danmu/{uname}/{title}")
    save_dir.mkdir(parents=True, exist_ok=True)

    file_path = save_dir / f"{bv_id}_{time_str}_danmu.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"弹幕数据已保存: {file_path}")

    #修bug 新增====================================
    cfg.DANMAKU_FILE = f"{cfg.DANMAKU_DIR}/{uname}/{title}/{bv_id}_{time_str}_danmu.json"

    print(f"更新全局配置: cfg.DANMAKU_FILE = {cfg.DANMAKU_FILE}")
    #================================================


def save_report(report_data: dict, bv_id: str, video_info: list) -> str:
    """
    保存情绪分析报告（JSON 格式）
    video_info[0] = UID
    video_info[1] = uname
    video_info[2] = title

    保存路径: data/report/{uname}/{title}/{bv_id}_{time_str}_report.json
    返回最终保存的文件路径（字符串）
    """

    from datetime import datetime
    from pathlib import Path
    import json

    now = datetime.now()
    time_str = now.strftime("%Y%m%d_%H%M%S")

    uid = video_info[0]
    uname = video_info[1]
    title = video_info[2]

    data = {
        "name": uname,
        "bv_id": bv_id,
        "uid": uid,
        "uname": uname,
        "title": title,
        "report_time": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    data.update(report_data)

    save_dir = Path(f"data/report/{uname}/{title}")
    save_dir.mkdir(parents=True, exist_ok=True)

    file_path = save_dir / f"{bv_id}_{time_str}_report.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"分析报告已保存: {file_path}")

    
    return str(file_path)


 
def save_word_freq(freq: dict, bv_id: str, video_info: list) -> str:
    """
    保存关键词词频统计（JSON 格式）
    video_info[0] = UID
    video_info[1] = uname
    video_info[2] = title

    保存路径（与 save_report / save_results 同一套目录规则）:
        data/report/{uname}/{title}/{bv_id}_{time_str}_word_freq.json

    返回最终保存的文件路径（字符串）
    """
    now = datetime.now()
    time_str = now.strftime("%Y%m%d_%H%M%S")

    uname = video_info[1]
    title = video_info[2]

    save_dir = Path(f"data/report/{uname}/{title}")
    save_dir.mkdir(parents=True, exist_ok=True)

    file_path = save_dir / f"{bv_id}_{time_str}_word_freq.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(freq, f, ensure_ascii=False, indent=2)

    print(f"词频统计已保存: {file_path}")
    return str(file_path)


def save_results(df: pd.DataFrame, name: str, bv_id: str, video_info: list) -> str:
    """
    保存带情绪标签的标注结果 + 统计摘要
    video_info[0] = UID
    video_info[1] = uname
    video_info[2] = title

    保存路径（与 save_report 同一套目录规则，name 区分是 comments 还是 danmaku）:
        data/report/{uname}/{title}/{bv_id}_{time_str}_{name}_annotated.json
        data/report/{uname}/{title}/{bv_id}_{time_str}_{name}_summary.json

    返回标注结果文件的路径（字符串）
    """
    now = datetime.now()
    time_str = now.strftime("%Y%m%d_%H%M%S")

    uname = video_info[1]
    title = video_info[2]

    save_dir = Path(f"data/report/{uname}/{title}")
    save_dir.mkdir(parents=True, exist_ok=True)

    # 标注结果
    annotated_path = save_dir / f"{bv_id}_{time_str}_{name}_annotated.json"
    df.to_json(annotated_path, orient="records", force_ascii=False, indent=2)
    print(f"[save] {name} 已保存: {annotated_path}")

    # 简单统计摘要
    summary = {}
    for col in df.columns:
        if col.endswith("_label"):
            summary[col] = df[col].value_counts().to_dict()
    summary_path = save_dir / f"{bv_id}_{time_str}_{name}_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[save] 摘要已保存: {summary_path}")

    return str(annotated_path)
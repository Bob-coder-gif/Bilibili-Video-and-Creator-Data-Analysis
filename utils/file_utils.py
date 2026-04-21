import json
from pathlib import Path
from datetime import datetime
import os


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
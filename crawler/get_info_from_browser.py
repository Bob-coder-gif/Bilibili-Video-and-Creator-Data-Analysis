"""
    get_info_from_browser.py

    修改时间：
        2026-04-21
------------------------------
主要修改内容：
    从浏览器中使用playerwright技术获取视频,up主,cid等信息

===============================
    
"""

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
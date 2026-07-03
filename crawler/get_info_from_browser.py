"""
    get_info_from_browser.py

    修改时间：
        2026-04-21
------------------------------
主要修改内容：
    从浏览器中使用playerwright技术获取视频,up主,cid等信息

    2026-06-21 修改：
    顺手把同一次 /x/web-interface/view 请求里的 stat 字段
    （view/danmaku/reply/favorite/coin/share/like 等）写入
    config.CURRENT_VIDEO_STAT，不需要再额外发一次请求。

    2026-06-22 修改（第二阶段重构）：
    把 stat 写全局变量这件事改成显式返回值。get_video_info() 现在返回
    (video_info, stat) 两个值，调用方（crawler_pipeline）接住后放进 task
    字典往下传，不再依赖 config 全局变量。
    video_info 本身的结构 [UID, uname, title] 完全不变，
    仍可用 video_info[0]/[1]/[2] 索引，向后兼容旧的调用方式。
    为兼容只想要 video_info、不关心 stat 的旧调用代码，
    cfg.CURRENT_VIDEO_STAT 这一处全局变量写入暂时保留，不强制删除，
    但新代码请优先使用返回值里的 stat，不要依赖这个全局变量。
===============================
    
"""

import requests
import config.config as cfg


def get_video_info(bv_id) -> tuple[list[str], dict]:
    """
    获取UP主UID,uname,title等信息，以及视频 stat 数据

    video_info[0] = UID
    video_info[1] = uname  
    video_info[2] = title

    返回:
        (video_info, stat)
        video_info: [UID, uname, title]  —— 结构与之前完全一致
        stat: {"view":.., "danmaku":.., "reply":.., "favorite":..,
               "coin":.., "share":.., "like":..}
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

    # ---------- 提取这次请求里的 stat ----------
    raw_stat = data.get("data", {}).get("stat", {})
    stat = {
        "view":     raw_stat.get("view", 0),
        "danmaku":  raw_stat.get("danmaku", 0),
        "reply":    raw_stat.get("reply", 0),
        "favorite": raw_stat.get("favorite", 0),
        "coin":     raw_stat.get("coin", 0),
        "share":    raw_stat.get("share", 0),
        "like":     raw_stat.get("like", 0),
    }

    # 兼容旧代码：仍顺手写一份到全局变量。
    # 新代码（如 crawler_pipeline）应优先使用返回值里的 stat，
    # 不要依赖这个全局变量——并发场景下它可能被后到的请求覆盖。
    cfg.CURRENT_VIDEO_STAT = stat
    # ----------------------------------------------------------

    return result, stat

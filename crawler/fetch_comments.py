"""
fetch_comments.py

功能：
    获取B站单视频评论

使用技术：
    - requests（HTTP请求）
    - Bilibili Web API逆向
    - 分页抓取

修改时间：
    2026-04-06
"""

import requests


def bv_to_aid(bv):
    import requests

    url = "https://api.bilibili.com/x/web-interface/view"
    params = {"bvid": bv}

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.bilibili.com/"
    }

    resp = requests.get(url, params=params, headers=headers)

    # 👉 加这个调试（非常重要）
    if resp.status_code != 200:
        print("请求失败:", resp.status_code)
        print(resp.text)
        return None

    try:
        data = resp.json()
    except Exception as e:
        print("JSON解析失败，返回内容：")
        print(resp.text[:200])
        return None

    return data["data"]["aid"]

def fetch_comments(bv_id, max_page=100):
    import requests

    aid = bv_to_aid(bv_id)
    comments = []

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.bilibili.com/"
    }

    for page in range(1, max_page + 1):
        url = "https://api.bilibili.com/x/v2/reply/main"

        params = {
            "type": 1,
            "oid": aid,
            "next": page,
            "mode": 3   # ⭐ 改成时间排序（更多评论）
        }

        resp = requests.get(url, params=params, headers=headers)

        try:
            data = resp.json()
        except:
            print("解析失败")
            break

        replies = data.get("data", {}).get("replies")

        if not replies:
            print(f"第 {page} 页没有数据，停止")
            break

        print(f"正在抓第 {page} 页")
    
        for item in replies:
            try:
                comments.append({
                "text": item["content"]["message"],
                "like": item.get("like", 0)
            })
            except:
                continue



    print("总评论数:", len(comments))
    return comments
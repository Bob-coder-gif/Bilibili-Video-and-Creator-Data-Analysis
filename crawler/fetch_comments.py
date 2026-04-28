"""
fetch_comments.py

bilibili网页页面内容说明：
commentapp-> 评论区最外层容器id
bili-comment-renderer-> 评论渲染
    在这个标签下可以找到评论和评论回复

修改时间：
    2026-04-06
--------------------------------------------
使用技术：
    - requests（HTTP请求）
    - Bilibili Web API逆向
    - 分页抓取

===========================================

修改时间：
    2026-04-20
--------------------------------------------
功能：
    获取B站单视频所有评论（半永久版）

核心思路：
    不自己构造API请求，而是让真实浏览器加载页面并滚动，
    同时拦截浏览器自己发出的评论API响应。
    这样无论B站怎么改风控参数、签名算法，都无需修改代码。

使用技术：
    - Playwright（浏览器自动化 + 网络拦截）
    - 持久化登录态（避免重复登录）

用法（在其他文件中导入）：
    from fetch_comments import fetch_comments
    data = fetch_comments("BV1xx411c7mD", max_count=0)

============================================

修改时间：
    2026-04-21
--------------------------------------------
修改内容：
    增加了自动发现评论API的功能，不再需要预先知道API路径，只要B站的评论API返回的JSON里还有 "replies" 这个key，就能自动发现并抓取。
    将026-4-20版本中存在的“不能爬取重复评论”问题修复了
    增加了评论作者的UID和用户名的抓取，方便后续分析使用。

============================================

修改时间：
    2026-04-23--2026-04-24
--------------------------------------------
修改内容：
    1. 新增了爬取评论回复的功能。现在不仅能爬取主评论，还能爬取每条主评论下的回复，并且将回复嵌套在对应主评论的字典里，形成清晰的层级结构。
    2. 修改了数据结构，将评论存储在一个字典里，key是评论ID（rpid），value是一个包含评论内容、点赞数、用户名等信息的字典。这样可以更方便地处理评论和回复的关系。
    3. 在抓取回复时，将回复也存储在对应主评论的字典里，形成嵌套结构，方便后续分析和展示。
    

============================================

"""

from playwright.sync_api import sync_playwright
import random
import os
import time
from crawler.bilibili_state import save_login_state

# ── 配置 ─────────────────────────────────────────────────────────────────────
STORAGE_PATH = "./bilibili_data/bilibili_state.json"
 
# 用于识别"这个响应是评论数据"的特征字段
# 只要B站评论API返回的JSON里还有 "replies" 这个key，就能自动发现
# （这比API路径稳定得多，基本不会变）
COMMENT_SIGNATURE = "replies"
#预添加
REPLAY_SIGNATURE = "replies"

# ─────────────────────────────────────────────────────────────────────────────
 

 
def fetch_comments(bv_id: str, max_count: int = 0) -> list[dict]:
    """
    抓取指定BV号视频的评论。
 
    参数：
        bv_id     : 视频BV号，例如 "BV1xx411c7mD"
        max_count : 最多收集多少条，0 = 不限制（抓全部）
 
    返回：
        [{"text": "评论内容", "like": 点赞数}, ...]
    """
    if not os.path.exists(STORAGE_PATH):
        save_login_state()
 
    comments = {}

    detected_api = None   # 动态发现的评论API路径（去掉query参数后的纯路径）
    reply_api    = None   # (暂时没有找到稳定获取的方法)

    replies_to_fetch = []  # 存储待抓取的回复API链接


    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            storage_state=STORAGE_PATH,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()

        """
            FOR CONTRAST:

            ROOT API:
            https://api.bilibili.com/x/v2/reply/wbi/main?oid=384634124&type=1&mode=3&pagination_str=%7B%22offset%22:%22%22%7D&plat=1&seek_rpid=&web_location=1315875&w_rid=b67feef3024b98d0dba1f973c27d3577&wts=1776936375        
            
            SON API:
            https://api.bilibili.com/x/v2/reply/reply?oid=384634124&type=1&root=299637885936&ps=10&pn=1&web_location=333.788
        
        """

        # ── 动态拦截：自动发现评论API + 收集数据
        def on_response(response):
            nonlocal detected_api
            nonlocal reply_api
 
            # 跳过明显无关的资源（图片、字体、CSS、JS等）
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                return
 
            try:
                data = response.json()
            except Exception:
                return
 
            # 判断这个JSON响应是否包含评论数据特征
            replies = (data.get("data")or {}).get(COMMENT_SIGNATURE)
            if not replies:
                return
 
            # 第一次发现评论API时，记录路径并打印
            if detected_api is None:
                # 只保留路径部分，去掉 query 参数（?type=1&oid=...）
                print(f"response：{response.url}")
                detected_api = response.url.split("?")[0]
                print(f"自动发现评论API：{detected_api}")
                reply_api_prefix = detected_api.replace("wbi/main", "reply")
                print(f"自动推测回复API：{reply_api_prefix}")

 
            # 收集评论
            for item in replies:
                try:
                    text = item.get("content", {}).get("message", "").strip()
                    like = item.get("like", 0)
                    mid = item.get("mid", "")
                    name = item.get("member", {}).get("uname", "")
                    rpid = item.get("rpid", "") # 评论ID
                    oid = item.get("oid", "")   # 视频OID
                    type_ = item.get("type", 1) # 类型

                    print("正确爬取到一条评论，正在做格式化处理...")

                    if text:
                        print("正在尝试格式化评论...")
                        comments[rpid] = {
                            "type": "root", # 标记为主评论
                            "mid": mid,
                            "text": text,
                            "like": like,
                            "name": name,
                            "replies": [], # 用于存储回复
                        }

                        print(f"收集到评论：{text}（点赞 {like}，用户 {name}）")

                    # 检查是否有回复
                    # sub_reply_entry_text 存在通常意味着有回复，例如 "共10条回复"
                    has_reply = bool(item.get("reply_control",{}).get("sub_reply_entry_text", ""))
                    
                    if has_reply and reply_api_prefix:
                        # 构造回复的API URL，加入队列
                        # 注意：这里只是构造URL，不发送请求，避免阻塞
                        url = f"{reply_api_prefix}?oid={oid}&type={type_}&root={rpid}&ps=10&pn=1"
                        replies_to_fetch.append(url)
                        
                except Exception as e:
                    print(f"   └─ 处理评论时出错: {e}") 
                    continue
 
        page.on("response", on_response)
        # ─────────────────────────────────────────────────────────────────────
 
        print(f"正在打开视频页：https://www.bilibili.com/video/{bv_id}")
        page.goto(
            f"https://www.bilibili.com/video/{bv_id}",
            timeout=60000,
            wait_until="domcontentloaded"
        )
        page.wait_for_timeout(4000)
 
        # ── 第一步：快速跳到底部，触发评论区初始化 ───────────────────────────
        print("跳转到评论区...")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)
 
        # 往回滚一点，确保评论区进入视口
        page.evaluate("window.scrollBy(0, -300)")
        page.wait_for_timeout(2000)
 
        # ── 第二步：等待评论容器出现 ──────────────────────────────────────────
        COMMENT_SELECTORS = [
            "#commentapp",
            ".comment-container",
            "[id^='comment']",
        ]
        for sel in COMMENT_SELECTORS:
            try:
                page.wait_for_selector(sel, timeout=5000)
                print(f"评论区已加载（selector: {sel}）")
                break
            except Exception:
                continue
 
        # ── 第三步：持续小步滚动，触发分页加载 ───────────────────────────────
        print("开始持续滚动加载评论...\n")
        stall_times = 0
        last_count  = 0
 
        while True:
            if max_count > 0 and len(comments) >= max_count:
                print(f"\n已达到设定上限 {max_count} 条，停止")
                break
 
            page.evaluate("window.scrollBy(0, window.innerHeight * 0.5)")
            page.wait_for_timeout(random.randint(2000, 4000))
 
            current_count = len(comments)
            print(f"  已收集：{current_count} 条评论", end="\r")
 
            if current_count == last_count:
                stall_times += 1
 
                if stall_times == 3:
                    print(f"\n  [卡住] 尝试重新触发加载...")
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2500)
                if stall_times >= 7:
                    print(f"\n连续无新数据，确认已到底，停止")
                    break
            else:
                stall_times = 0
                last_count  = current_count



        # ── 第四步：统一抓取回复 ───────────────────────────────────────────
        print(f"\n主评论抓取完成，开始抓取 {len(replies_to_fetch)} 个评论下的回复...")
 
                # 遍历队列，发起请求
        for idx, url in enumerate(replies_to_fetch):
            try:
                # 使用 context.request 复用浏览器的 Cookie
                resp = context.request.get(url)
                if resp.status == 200:
                    r_data = resp.json()
                    r_replies = (r_data.get("data") or {}).get("replies", [])
                    
                    for r_item in r_replies:
                        r_text = r_item.get("content", {}).get("message", "").strip()
                        r_like = r_item.get("like", 0)
                        r_mid = r_item.get("mid", "")
                        r_name = r_item.get("member", {}).get("uname", "")
                        r_root = r_item.get("root", "") 
                        if r_text:
                            comments[r_root]["replies"].append({
                                "type": "reply", # 标记为回复
                                "mid": r_mid,
                                "text": r_text,
                                "like": r_like,
                                "name": r_name,
                            })

                            print(f"   └─ 抓取到回复：{r_text[:20]}... (用户: {r_name})")
                else:
                    print(f"   └─ 抓取回复失败: {resp.status}")
                    pass
            except Exception as e:
                print(f"   └─ 请求异常: {e}")
                pass
       
            time.sleep(0.1)



        browser.close()


    result = comments if max_count == 0 else comments[:max_count]
    print(f"\n抓取完成，共收集 {len(result)} 条评论")
    return result
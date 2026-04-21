"""
fetch_comments.py

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

"""

from playwright.sync_api import sync_playwright
import random
import os
 
# ── 配置 ─────────────────────────────────────────────────────────────────────
STORAGE_PATH = "./bilibili_state/bilibili_state.json"
 
# 用于识别"这个响应是评论数据"的特征字段
# 只要B站评论API返回的JSON里还有 "replies" 这个key，就能自动发现
# （这比API路径稳定得多，基本不会变）
COMMENT_SIGNATURE = "replies"
# ─────────────────────────────────────────────────────────────────────────────
 
 
def save_login_state():
    """首次运行：打开浏览器让用户手动登录，保存Cookie。"""
    print("=" * 50)
    print("首次运行：请在弹出的浏览器中登录B站账号")
    print("登录完成后回到终端按回车键继续")
    print("=" * 50)
    with sync_playwright() as p:
        '''
            headless=False 让浏览器可见，方便用户登录。
            headless=True 则在后台运行，无法手动登录。
            new_context() 创建新的浏览器上下文，相当于新的独立浏览器环境。不受本地其他浏览器数据干扰
        '''
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page    = context.new_page()
        page.goto("https://www.bilibili.com")
        input("\n✅ 登录完成后按回车保存状态...")
        context.storage_state(path=STORAGE_PATH)
        browser.close()
    print(f"登录状态已保存到 {STORAGE_PATH}\n")
 
 
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
 
    comments    = []

    detected_api = None   # 动态发现的评论API路径（去掉query参数后的纯路径）
 
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
 
        # ── 动态拦截：自动发现评论API + 收集数据 ─────────────────────────────
        def on_response(response):
            nonlocal detected_api
 
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
                detected_api = response.url.split("?")[0]
                print(f"自动发现评论API：{detected_api}")
 
            # 收集评论
            for item in replies:
                try:
                    text = item.get("content", {}).get("message", "").strip()
                    like = item.get("like", 0)
                    mid  = item.get("mid", "")
                    name = item.get("member", {}).get("uname", "")

                    if text:
                        comments.append({"text": text, "like": like, "mid": mid, "name": name})
                except Exception:
                    continue
 
        page.on("response", on_response)
        # ─────────────────────────────────────────────────────────────────────
 
        print(f"正在打开视频页：https://www.bilibili.com/video/{bv_id}")
        # 超时时间从30秒延长到60秒，且不等待所有资源加载完，只等主文档
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
 
        page.wait_for_timeout(2000)
 
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
                    page.evaluate("window.scrollBy(0, -200)")
                    page.wait_for_timeout(2000)
 
                if stall_times >= 7:
                    print(f"\n连续无新数据，确认已到底，停止")
                    break
            else:
                stall_times = 0
                last_count  = current_count
 
        browser.close()
 
    result = comments if max_count == 0 else comments[:max_count]
    print(f"\n抓取完成，共收集 {len(result)} 条评论")
    return result
 
"""
fetch_comments.py

--------------------------------------------
使用技术：
    - requests（HTTP请求）
    - Bilibili Web API逆向
    - 分页抓取

修改时间：
    2026-04-06
--------------------------------------
    
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

修改时间：
    2026-04-20

--------------------------------------------

"""

from playwright.sync_api import sync_playwright
import json
import random
import os

# ── 配置 ─────────────────────────────────────────────────────────────────────
STORAGE_PATH = "./bilibili_state/bilibili_state.json"
COMMENT_API  = "api.bilibili.com/x/v2/reply"
# ─────────────────────────────────────────────────────────────────────────────


def save_login_state():
    """首次运行：打开浏览器让用户手动登录，保存Cookie。"""
    print("=" * 50)
    print("首次运行：请在弹出的浏览器中登录B站账号")
    print("登录完成后回到终端按回车键继续")
    print("=" * 50)
    with sync_playwright() as p:
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

    comments   = []
    seen_texts = set()

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

        # ── 拦截评论API响应 ───────────────────────────────────────────────────
        def on_response(response):
            if COMMENT_API not in response.url:
                return
            try:
                data    = response.json()
                replies = data.get("data", {}).get("replies") or []
                for item in replies:
                    text = item.get("content", {}).get("message", "").strip()
                    like = item.get("like", 0)
                    if text and text not in seen_texts:
                        seen_texts.add(text)
                        comments.append({"text": text, "like": like})
            except Exception:
                pass

        page.on("response", on_response)
        # ─────────────────────────────────────────────────────────────────────

        print(f"正在打开视频页：https://www.bilibili.com/video/{bv_id}")
        page.goto(f"https://www.bilibili.com/video/{bv_id}")
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
    print(f"\n✅ 抓取完成，共收集 {len(result)} 条评论")
    return result
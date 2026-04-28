"""
bilibili_state.py

修改时间：
    2026-4-26

功能：
    1. 首次运行：打开浏览器让用户手动登录，保存Cookie
        （从fetch_comment.py中提取出来，单独成文件，方便维护）。
"""

from playwright.sync_api import sync_playwright

#配置文件路径-----------------------------------------------
STORAGE_PATH = "./bilibili_data/bilibili_state.json"

 
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
        input("\n 登录完成后按回车保存状态...")
        context.storage_state(path=STORAGE_PATH)
        browser.close()
    print(f"登录状态已保存到 {STORAGE_PATH}\n")
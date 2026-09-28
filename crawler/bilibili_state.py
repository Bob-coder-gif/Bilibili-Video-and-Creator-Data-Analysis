"""
crawler/bilibili_state.py
登录态管理 + 浏览器启动

修改时间：
    2026-04-26  从 fetch_comments.py 中提取出来，单独成文件
    2026-06-21  print 改为 logger.info（首次登录提示必须始终显示）
    2026-06-22  新增 launch_browser()：引擎从 config 读取，失败自动降级到备用引擎；
                STORAGE_PATH 改为从 config 读取

修改时间：
    2026-09-28
----------------------------------
    1. 新增 has_login_state()，网页服务启动时先检查登录态（见 app/web.py）。
       原来是在后台 worker 线程里第一次爬评论时才发现没登录，然后在线程里
       等待终端 input()，网页上只会一直显示"正在爬取评论…"。
    2. 保存登录态前自动创建 bilibili_data/ 目录。
"""

import os

from playwright.sync_api import sync_playwright

import config.config as cfg
from utils.log_utils import get_logger

logger = get_logger()

STORAGE_PATH = cfg.STORAGE_PATH


def has_login_state() -> bool:
    return os.path.exists(STORAGE_PATH)


def launch_browser(p, headless: bool | None = None):
    """
    按 config 选择浏览器引擎启动；主引擎失败时尝试备用引擎。
    headless=None 时使用 config.HEADLESS。
    """
    if headless is None:
        headless = cfg.HEADLESS

    engine_name = getattr(cfg, "BROWSER_ENGINE", "chromium")
    fallback_name = getattr(cfg, "BROWSER_FALLBACK_ENGINE", None)
    engines = {"chromium": p.chromium, "firefox": p.firefox, "webkit": p.webkit}

    def _launch(name):
        engine = engines.get(name, p.chromium)
        # chromium 用新版 headless（特征更接近真实浏览器）；其它引擎不认这个参数
        if name == "chromium" and headless:
            return engine.launch(headless=True, args=["--headless=new"])
        return engine.launch(headless=headless)

    try:
        browser = _launch(engine_name)
        logger.debug(f"浏览器启动成功：{engine_name}")
        return browser
    except Exception as e:
        logger.warning(f"主用浏览器引擎 [{engine_name}] 启动失败：{e}")
        if not fallback_name or fallback_name == engine_name or fallback_name not in engines:
            raise
        logger.info(f"尝试切换到备用浏览器引擎：{fallback_name}")
        browser = _launch(fallback_name)
        logger.info(f"备用浏览器引擎 [{fallback_name}] 启动成功")
        return browser


def save_login_state():
    """打开可见浏览器让用户手动登录 B 站，然后保存 Cookie"""
    logger.info("=" * 50)
    logger.info("首次运行：请在弹出的浏览器中登录B站账号")
    logger.info("登录完成后回到终端按回车键继续")
    logger.info("=" * 50)

    os.makedirs(os.path.dirname(STORAGE_PATH) or ".", exist_ok=True)

    with sync_playwright() as p:
        # 登录必须能看到窗口，强制 headless=False，不受 config.HEADLESS 影响
        browser = launch_browser(p, headless=False)
        try:
            # new_context() 是独立的浏览器环境，不受本机其他浏览器数据干扰
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://www.bilibili.com")
            input("\n 登录完成后按回车保存状态...")
            context.storage_state(path=STORAGE_PATH)
        finally:
            browser.close()
    logger.info(f"登录状态已保存到 {STORAGE_PATH}\n")

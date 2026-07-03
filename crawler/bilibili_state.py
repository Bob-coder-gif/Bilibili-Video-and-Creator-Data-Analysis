"""
bilibili_state.py

修改时间：
    2026-4-26

功能：
    1. 首次运行：打开浏览器让用户手动登录，保存Cookie
        （从fetch_comment.py中提取出来，单独成文件，方便维护）。

修改时间：
    2026-06-21
----------------------------------
修改内容：
    print 改为 logger.info——这几条是首次登录时给用户看的关键提示，
    必须始终显示，所以仍然用 info 级别（不是 debug）。

修改时间：
    2026-06-22
----------------------------------
修改内容：
    1. 新增 launch_browser()：浏览器类型不再写死 p.chromium，
       统一从 config.BROWSER_ENGINE 读取，启动失败时自动降级到
       config.BROWSER_FALLBACK_ENGINE（例如 chromium 挂了自动换 firefox）。
       fetch_comments.py 直接复用这个函数，不用各写一份。
    2. STORAGE_PATH 改为从 config 读取（变量名不变，只是来源换了）。
"""

from playwright.sync_api import sync_playwright
from utils.log_utils import get_logger
import config.config as cfg

logger = get_logger()

# 兼容旧代码：变量名保持 STORAGE_PATH，只是来源换成了 config，方便统一管理
STORAGE_PATH = cfg.STORAGE_PATH


# def launch_browser(p, headless: bool = None):
#     """
#     按 config.BROWSER_ENGINE 启动浏览器，失败时自动尝试 config.BROWSER_FALLBACK_ENGINE。

#     新增函数，供 bilibili_state.py / fetch_comments.py 共用，
#     避免每个文件各写一份 p.chromium.launch(...)。

#     参数：
#         p        : sync_playwright() 上下文里的 playwright 实例
#         headless : 不传则用 config.HEADLESS
#     """
#     if headless is None:
#         headless = cfg.HEADLESS

#     engine_name = getattr(cfg, "BROWSER_ENGINE", "chromium")
#     fallback_name = getattr(cfg, "BROWSER_FALLBACK_ENGINE", None)

#     engines = {
#         "chromium": p.chromium,
#         "firefox": p.firefox,
#         "webkit": p.webkit,
#     }

#     primary = engines.get(engine_name, p.chromium)

#     try:
#         browser = primary.launch(headless=headless)
#         logger.debug(f"浏览器启动成功：{engine_name}")
#         return browser
#     except Exception as e:
#         logger.warning(f"主用浏览器引擎 [{engine_name}] 启动失败：{e}")

#         if fallback_name and fallback_name != engine_name and fallback_name in engines:
#             logger.info(f"尝试切换到备用浏览器引擎：{fallback_name}")
#             try:
#                 browser = engines[fallback_name].launch(headless=headless)
#                 logger.info(f"备用浏览器引擎 [{fallback_name}] 启动成功")
#                 return browser
#             except Exception as e2:
#                 logger.warning(f"备用浏览器引擎 [{fallback_name}] 也启动失败：{e2}")
#                 raise
#         else:
#             raise


def launch_browser(p, headless: bool = None):
    if headless is None:
        headless = cfg.HEADLESS

    engine_name = getattr(cfg, "BROWSER_ENGINE", "chromium")
    fallback_name = getattr(cfg, "BROWSER_FALLBACK_ENGINE", None)

    engines = {
        "chromium": p.chromium,
        "firefox": p.firefox,
        "webkit": p.webkit,
    }

    primary = engines.get(engine_name, p.chromium)

    # chromium 用新版 headless（特征更接近真实浏览器，不易被 B 站识别为无头），
    # 其它引擎不认 --headless=new 参数，保持默认
    def _launch(engine, name):
        if name == "chromium" and headless:
            return engine.launch(headless=True, args=["--headless=new"])
        return engine.launch(headless=headless)

    try:
        browser = _launch(primary, engine_name)
        logger.debug(f"浏览器启动成功：{engine_name}")
        return browser
    except Exception as e:
        logger.warning(f"主用浏览器引擎 [{engine_name}] 启动失败：{e}")

        if fallback_name and fallback_name != engine_name and fallback_name in engines:
            logger.info(f"尝试切换到备用浏览器引擎：{fallback_name}")
            try:
                browser = _launch(engines[fallback_name], fallback_name)
                logger.info(f"备用浏览器引擎 [{fallback_name}] 启动成功")
                return browser
            except Exception as e2:
                logger.warning(f"备用浏览器引擎 [{fallback_name}] 也启动失败：{e2}")
                raise
        else:
            raise


def save_login_state():
    """首次运行：打开浏览器让用户手动登录，保存Cookie。"""
    logger.info("=" * 50)
    logger.info("首次运行：请在弹出的浏览器中登录B站账号")
    logger.info("登录完成后回到终端按回车键继续")
    logger.info("=" * 50)
    with sync_playwright() as p:
        '''
            headless=False 让浏览器可见，方便用户登录。
            headless=True 则在后台运行，无法手动登录。
            new_context() 创建新的浏览器上下文，相当于新的独立浏览器环境。不受本地其他浏览器数据干扰
        '''
        # 登录必须能看到窗口，这里强制 headless=False，不受 config.HEADLESS 影响
        browser = launch_browser(p, headless=False)
        context = browser.new_context()
        page    = context.new_page()
        page.goto("https://www.bilibili.com")
        input("\n 登录完成后按回车保存状态...")
        context.storage_state(path=STORAGE_PATH)
        browser.close()
    logger.info(f"登录状态已保存到 {STORAGE_PATH}\n")
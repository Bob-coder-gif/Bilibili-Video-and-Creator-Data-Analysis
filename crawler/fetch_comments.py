"""
fetch_comments.py

bilibili网页页面内容说明：
commentapp-> 评论区最外层容器id
bili-comment-renderer-> 评论渲染
    在这个标签下可以找到评论和评论回复

历史修改记录（保留）：
    2026-04-06  requests + API 逆向 + 分页抓取（初版）
    2026-04-20  改为 Playwright 浏览器加载 + 网络拦截（半永久版）
    2026-04-21  自动发现评论 API；修复重复评论问题；抓取作者 UID/用户名
    2026-04-23~24  新增爬取回复并嵌套进主评论；评论改为以 rpid 为 key 的字典
    2026-06-21  print 改 logger（debug/info/warning 分级）；关键计数写 log_event
    2026-06-27  新增 progress 进度回调（实时条数）

核心思路：
    不自己构造 API 请求，而是让真实浏览器加载页面并滚动，
    同时拦截浏览器自己发出的评论 API 响应。

============================================
修改时间：
    2026-06-27（健壮性增强）
--------------------------------------------
修改内容（解决"连续跑多个任务时，部分任务爬到 0 条评论"的问题）：
    原因：原代码打开页面后只死等固定的 1~2 秒就开始滚动。但 B 站评论区是 JS
    异步加载的，连续跑多个任务时 B 站响应会变慢，固定的短等待经常赶不上评论区
    初始化，导致一个评论 API 都没拦截到 → 0 条。

    本次改动：
      1. page.goto 后改为等待网络基本空闲（networkidle），并把评论区初始化的
         等待时间放宽，给异步加载留足时间。
      2. 新增"整页重试"：如果滚动若干轮后仍然 0 条评论且没发现评论 API，
         自动重新加载页面再试一次（最多 _MAX_PAGE_RETRY 次），
         覆盖"这次加载恰好没出来"的偶发情况。
      3. 函数返回前加一个小随机延时，拉开连续任务之间的请求间隔，
         降低被 B 站限流的概率。
    这些改动不影响命令行单独跑，也不改变评论数据本身的结构。
============================================
修改时间：
    2026-09-28（降低风控风险）
--------------------------------------------
修改内容（解决"评论抓完后获取视频信息报 412"的问题）：
      1. 页面加载完成后，顺手从 window.__INITIAL_STATE__.videoData 读取视频信息
         并缓存给 get_video_info 使用，省掉一次单独的 view 接口请求。
      2. 回复抓取的间隔从固定 0.1s 改为随机 _REPLY_DELAY 秒。原来几百个回复请求
         在短时间内连续发出，是触发 IP 风控的主要原因。
      3. 回复请求遇到 HTTP 412 或风控业务码时立即停止抓取剩余回复，
         已抓到的数据保留，避免风控期间继续请求把封禁时间拉长。
      4. 修复：max_count > 0 时对 dict 做切片会报 TypeError。
      5. 修复：回复的 root 不在 comments 中（如主评论文本为空未收录）时
         会 KeyError，导致该条回复所在批次剩余回复全部丢失。
============================================
修改时间：
    2026-09-28（清理 + 补字段）
--------------------------------------------
      1. 评论和回复新增 "timestamp" 字段（B 站接口的 ctime，发布时间）。
         原来没存，loader 读到的评论时间全是空，report 里的
         comment_time_trend（按日期的情绪趋势）永远是空列表。
      2. 未登录时直接抛出明确的错误，不再在这里调用 save_login_state()。
         网页模式下这里运行在后台线程，原来会卡在终端 input() 上，
         网页只显示"正在爬取评论…"。登录改为在 app/web.py 启动时完成。
      3. UA 和风控业务码改为复用 utils.http_utils 里的定义，不再各写一份；
         删除未使用的 REPLAY_SIGNATURE、reply_api 变量。
      4. 浏览器改为 try/finally 关闭；无头模式改为读取 config.HEADLESS。
      5. "打开页面 + 整页重试"拆成 _open_page_and_wait_comments，主函数只保留流程。
============================================
"""

import random
import time

from playwright.sync_api import sync_playwright

import config.config as cfg
from crawler.bilibili_state import has_login_state, launch_browser
from crawler.get_info_from_browser import cache_video_data, JS_READ_VIDEO_DATA
from utils.http_utils import USER_AGENT, RISK_CODES, BiliLoginRequiredError
from utils.log_utils import get_logger, log_event

logger = get_logger()

# ── 配置 ─────────────────────────────────────────────────────────────────────
STORAGE_PATH = cfg.STORAGE_PATH

# 评论 API 响应的特征字段：data.replies
COMMENT_SIGNATURE = "replies"

# 抓回复时，每处理多少个就汇报一次进度
_REPLY_REPORT_EVERY = 20

# 两次回复请求之间的随机间隔（秒）。调小会更快，但更容易触发风控
_REPLY_DELAY = (0.5, 1.2)

# 整页重试次数：滚动若干轮仍 0 条评论且没发现评论 API 时，重新加载页面重试
_MAX_PAGE_RETRY = 2

# 连续任务之间的随机间隔（秒），降低被限流概率
_BETWEEN_TASK_DELAY = (2.0, 5.0)

# ─────────────────────────────────────────────────────────────────────────────


def _report(progress, stage, message="", **extra):
    """安全调用进度回调：progress 为 None 时什么也不做"""
    if progress is not None:
        progress(stage, message, **extra)


def _parse_item(item: dict, item_type: str) -> dict:
    """把 B 站评论 / 回复条目转成项目内部结构"""
    return {
        "type": item_type,
        "mid": item.get("mid", ""),
        "text": (item.get("content") or {}).get("message", "").strip(),
        "like": item.get("like", 0),
        "name": (item.get("member") or {}).get("uname", ""),
        "timestamp": item.get("ctime"),
    }


def _open_page_and_wait_comments(page, bv_id: str, has_data) -> None:
    """
    打开视频页并触发评论区加载，带"整页重试"：
    若某次加载后仍未捕获到评论数据（has_data() 为 False），重新加载再试。
    """
    comment_selectors = ["#commentapp", ".comment-container", "[id^='comment']"]

    for attempt in range(1, _MAX_PAGE_RETRY + 2):  # 首次 + 最多 _MAX_PAGE_RETRY 次重试
        logger.debug(f"正在打开视频页（第 {attempt} 次尝试）：https://www.bilibili.com/video/{bv_id}")
        page.goto(
            f"https://www.bilibili.com/video/{bv_id}",
            timeout=60000,
            wait_until="domcontentloaded",
        )

        # 顺手读取页面里的视频信息，缓存给 get_video_info，省一次 view 接口请求
        try:
            if cache_video_data(bv_id, page.evaluate(JS_READ_VIDEO_DATA)):
                logger.debug("已从页面缓存视频信息")
        except Exception as e:
            logger.debug(f"读取页面视频信息失败（不影响评论抓取）: {e}")

        # 1) 等网络基本空闲，给页面异步资源加载留时间
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            logger.debug("等待 networkidle 超时，继续尝试触发评论区")

        # 2) 跳到底部触发评论区初始化
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)
        page.evaluate("window.scrollBy(0, -300)")
        page.wait_for_timeout(1500)

        # 3) 等评论容器出现
        for sel in comment_selectors:
            try:
                page.wait_for_selector(sel, timeout=5000)
                logger.debug(f"评论区已加载（selector: {sel}）")
                break
            except Exception:
                continue

        # 4) 给评论 API 真正发出来的时间
        page.wait_for_timeout(2000)

        if has_data():
            logger.debug(f"第 {attempt} 次尝试已捕获到评论数据，进入滚动收集")
            return

        if attempt <= _MAX_PAGE_RETRY:
            logger.warning(f"第 {attempt} 次未捕获到评论数据，重新加载页面重试…")
            log_event("fetch_comments_retry", bv_id=bv_id, attempt=attempt)
            page.wait_for_timeout(random.randint(1500, 3000))
        else:
            logger.warning("多次尝试仍未捕获到评论数据，可能该视频确实无评论或被限流")
            log_event("fetch_comments_no_data", bv_id=bv_id)


def fetch_comments(bv_id: str, max_count: int = 0, progress=None) -> dict:
    """
    抓取指定BV号视频的评论（含每条主评论下第一页回复）。

    参数：
        bv_id     : 视频BV号
        max_count : 最多收集多少条主评论，0 = 不限制
        progress  : 可选进度回调；None 时不汇报

    返回：
        评论字典 {rpid: {"type","mid","text","like","name","timestamp","replies":[...]}}
    """
    if not has_login_state():
        raise BiliLoginRequiredError(
            f"未找到 B 站登录态文件 {STORAGE_PATH}，请重启网页服务，按提示在弹出的浏览器中登录"
        )

    comments = {}
    replies_to_fetch = []
    detected_api = None
    reply_api_prefix = None
    reply_collected = 0
    reply_fail_count = 0
    reply_aborted = False   # 是否因风控提前停止

    # ── 动态拦截：自动发现评论 API + 收集数据
    def on_response(response):
        nonlocal detected_api, reply_api_prefix

        if "json" not in response.headers.get("content-type", ""):
            return
        try:
            data = response.json()
        except Exception:
            return

        replies = (data.get("data") or {}).get(COMMENT_SIGNATURE)
        if not replies:
            return

        if detected_api is None:
            detected_api = response.url.split("?")[0]
            reply_api_prefix = detected_api.replace("wbi/main", "reply")
            logger.debug(f"自动发现评论API：{detected_api}，推测回复API：{reply_api_prefix}")
            log_event("comment_api_detected", api=detected_api, reply_api=reply_api_prefix)

        for item in replies:
            try:
                rpid = item.get("rpid", "")
                parsed = _parse_item(item, "root")
                if parsed["text"]:
                    parsed["replies"] = []
                    comments[rpid] = parsed
                    logger.debug(f"收集到评论：{parsed['text']}（点赞 {parsed['like']}，用户 {parsed['name']}）")

                has_reply = bool((item.get("reply_control") or {}).get("sub_reply_entry_text", ""))
                if has_reply and reply_api_prefix:
                    url = (f"{reply_api_prefix}?oid={item.get('oid', '')}"
                           f"&type={item.get('type', 1)}&root={rpid}&ps=10&pn=1")
                    replies_to_fetch.append(url)
            except Exception as e:
                logger.warning(f"处理评论时出错: {e}")

    with sync_playwright() as p:
        browser = launch_browser(p)
        try:
            context = browser.new_context(
                storage_state=STORAGE_PATH,
                user_agent=USER_AGENT,
                viewport={"width": 1366, "height": 768},
            )
            page = context.new_page()
            page.on("response", on_response)

            _open_page_and_wait_comments(
                page, bv_id, has_data=lambda: detected_api is not None or len(comments) > 0
            )

            # ── 持续小步滚动，触发分页加载
            _report(progress, "crawl_comments", "正在爬取评论…")
            stall_times = 0
            last_count = 0

            while True:
                if max_count > 0 and len(comments) >= max_count:
                    logger.debug(f"已达到设定上限 {max_count} 条，停止")
                    break

                page.evaluate("window.scrollBy(0, window.innerHeight * 0.5)")
                page.wait_for_timeout(random.randint(1000, 2000))

                current_count = len(comments)
                logger.debug(f"已收集：{current_count} 条评论")
                _report(progress, "crawl_comments",
                        f"正在爬取评论…已 {current_count} 条",
                        comment_count=current_count)

                if current_count == last_count:
                    stall_times += 1
                    if stall_times == 3:
                        logger.debug("[卡住] 尝试重新触发加载...")
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(1000)
                    if stall_times >= 7:
                        logger.debug("连续无新数据，确认已到底，停止")
                        break
                else:
                    stall_times = 0
                    last_count = current_count

            # ── 统一抓取回复
            total = len(replies_to_fetch)
            logger.info(f"主评论抓取完成，共 {len(comments)} 条，开始抓取 {total} 个评论下的回复...")
            _report(progress, "crawl_comments",
                    f"主评论爬取完成，共 {len(comments)} 条，开始抓取回复…",
                    comment_count=len(comments))

            for idx, url in enumerate(replies_to_fetch):
                try:
                    resp = context.request.get(url)

                    if resp.status == 412:
                        reply_aborted = True
                        logger.warning(f"抓取回复触发风控（HTTP 412），停止抓取剩余 {total - idx} 个评论的回复")
                        break

                    if resp.status != 200:
                        reply_fail_count += 1
                        logger.debug(f"抓取回复失败: HTTP {resp.status}")
                    else:
                        r_data = resp.json()
                        if r_data.get("code") in RISK_CODES:
                            reply_aborted = True
                            logger.warning(f"抓取回复触发风控（业务码 {r_data.get('code')}），停止抓取剩余回复")
                            break

                        for r_item in (r_data.get("data") or {}).get("replies") or []:
                            reply = _parse_item(r_item, "reply")
                            root_comment = comments.get(r_item.get("root", ""))
                            if reply["text"] and root_comment is not None:
                                root_comment["replies"].append(reply)
                                reply_collected += 1
                except Exception as e:
                    reply_fail_count += 1
                    logger.debug(f"请求异常: {e}")

                if (idx + 1) % _REPLY_REPORT_EVERY == 0 or idx + 1 == total:
                    _report(progress, "crawl_comments",
                            f"正在抓取回复… {idx + 1}/{total}（已收集 {reply_collected} 条回复）",
                            reply_done=idx + 1, reply_total=total,
                            reply_collected=reply_collected)

                time.sleep(random.uniform(*_REPLY_DELAY))
        finally:
            browser.close()

    if reply_fail_count:
        logger.warning(f"{reply_fail_count} 个回复请求失败，详情见 debug 日志")

    # 连续任务之间留一个随机间隔，降低被 B 站限流的概率
    time.sleep(random.uniform(*_BETWEEN_TASK_DELAY))

    result = dict(list(comments.items())[:max_count]) if max_count > 0 else comments

    logger.info(f"评论抓取完成，共 {len(result)} 条主评论，{reply_collected} 条回复")
    log_event(
        "fetch_comments_done",
        bv_id=bv_id,
        comment_count=len(result),
        reply_count=reply_collected,
        reply_fail_count=reply_fail_count,
        reply_aborted=reply_aborted,
    )
    return result

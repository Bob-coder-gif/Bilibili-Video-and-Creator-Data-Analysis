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
"""

from playwright.sync_api import sync_playwright
import random
import os
import time
import config.config as cfg
from crawler.bilibili_state import save_login_state, launch_browser
from utils.log_utils import get_logger, log_event

logger = get_logger()

# ── 配置 ─────────────────────────────────────────────────────────────────────
STORAGE_PATH = cfg.STORAGE_PATH

COMMENT_SIGNATURE = "replies"
REPLAY_SIGNATURE = "replies"

# 抓回复时，每处理多少个就汇报一次进度
_REPLY_REPORT_EVERY = 20

# 整页重试次数：滚动若干轮仍 0 条评论且没发现评论 API 时，重新加载页面重试
_MAX_PAGE_RETRY = 2

# 连续任务之间的随机间隔（秒），降低被限流概率
_BETWEEN_TASK_DELAY = (2.0, 5.0)

# ─────────────────────────────────────────────────────────────────────────────


def _report(progress, stage, message="", **extra):
    """安全调用进度回调：progress 为 None 时什么也不做"""
    if progress is not None:
        progress(stage, message, **extra)


def fetch_comments(bv_id: str, max_count: int = 0, progress=None) -> list[dict]:
    """
    抓取指定BV号视频的评论。

    参数：
        bv_id     : 视频BV号
        max_count : 最多收集多少条，0 = 不限制（抓全部）
        progress  : 可选进度回调；None 时不汇报

    返回：
        评论字典（key=rpid）。
    """
    if not os.path.exists(STORAGE_PATH):
        save_login_state()

    comments = {}

    detected_api = None
    reply_api    = None
    reply_api_prefix = None

    replies_to_fetch = []

    with sync_playwright() as p:
        browser = launch_browser(p, headless=True)
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

        # ── 动态拦截：自动发现评论API + 收集数据
        def on_response(response):
            nonlocal detected_api
            nonlocal reply_api
            nonlocal reply_api_prefix

            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                return

            try:
                data = response.json()
            except Exception:
                return

            replies = (data.get("data") or {}).get(COMMENT_SIGNATURE)
            if not replies:
                return

            if detected_api is None:
                logger.debug(f"response：{response.url}")
                detected_api = response.url.split("?")[0]
                reply_api_prefix = detected_api.replace("wbi/main", "reply")
                logger.debug(f"自动发现评论API：{detected_api}")
                logger.debug(f"自动推测回复API：{reply_api_prefix}")
                log_event("comment_api_detected", api=detected_api, reply_api=reply_api_prefix)

            for item in replies:
                try:
                    text = item.get("content", {}).get("message", "").strip()
                    like = item.get("like", 0)
                    mid = item.get("mid", "")
                    name = item.get("member", {}).get("uname", "")
                    rpid = item.get("rpid", "")
                    oid = item.get("oid", "")
                    type_ = item.get("type", 1)

                    if text:
                        comments[rpid] = {
                            "type": "root",
                            "mid": mid,
                            "text": text,
                            "like": like,
                            "name": name,
                            "replies": [],
                        }
                        logger.debug(f"收集到评论：{text}（点赞 {like}，用户 {name}）")

                    has_reply = bool(item.get("reply_control", {}).get("sub_reply_entry_text", ""))
                    if has_reply and reply_api_prefix:
                        url = f"{reply_api_prefix}?oid={oid}&type={type_}&root={rpid}&ps=10&pn=1"
                        replies_to_fetch.append(url)

                except Exception as e:
                    logger.warning(f"处理评论时出错: {e}")
                    continue

        page.on("response", on_response)

        # ====================================================================
        # 打开页面 + 触发评论区加载，带"整页重试"：
        # 若某次加载后滚动若干轮仍 0 条评论且没发现评论 API，重新加载再试。
        # ====================================================================
        for attempt in range(1, _MAX_PAGE_RETRY + 2):  # 首次 + 最多 _MAX_PAGE_RETRY 次重试
            logger.debug(f"正在打开视频页（第 {attempt} 次尝试）：https://www.bilibili.com/video/{bv_id}")
            page.goto(
                f"https://www.bilibili.com/video/{bv_id}",
                timeout=60000,
                wait_until="domcontentloaded",
            )

            # 1) 先等网络基本空闲，给页面异步资源加载留时间（连续跑时尤其重要）
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                # 网络一直不空闲也没关系，继续往下，靠后面的滚动+等待兜底
                logger.debug("等待 networkidle 超时，继续尝试触发评论区")

            # 2) 跳到底部触发评论区初始化，并多给一点等待时间
            logger.debug("跳转到评论区...")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            page.evaluate("window.scrollBy(0, -300)")
            page.wait_for_timeout(1500)

            # 3) 等评论容器出现（等待时间放宽到 5 秒）
            COMMENT_SELECTORS = ["#commentapp", ".comment-container", "[id^='comment']"]
            for sel in COMMENT_SELECTORS:
                try:
                    page.wait_for_selector(sel, timeout=5000)
                    logger.debug(f"评论区已加载（selector: {sel}）")
                    break
                except Exception:
                    continue

            # 4) 再等一会，给评论 API 真正发出来的时间
            page.wait_for_timeout(2000)

            # 判断这次加载是否成功"摸到"了评论：发现了评论 API 或已收到评论
            if detected_api is not None or len(comments) > 0:
                logger.debug(f"第 {attempt} 次尝试已捕获到评论数据，进入滚动收集")
                break

            # 没摸到评论：如果还有重试机会，重新加载；否则放弃（可能是真的没评论）
            if attempt <= _MAX_PAGE_RETRY:
                logger.warning(f"第 {attempt} 次未捕获到评论数据，重新加载页面重试…")
                log_event("fetch_comments_retry", bv_id=bv_id, attempt=attempt)
                page.wait_for_timeout(random.randint(1500, 3000))
            else:
                logger.warning("多次尝试仍未捕获到评论数据，可能该视频确实无评论或被限流")
                log_event("fetch_comments_no_data", bv_id=bv_id)

        # ── 持续小步滚动，触发分页加载
        logger.info("开始爬取评论...")
        _report(progress, "crawl_comments", "正在爬取评论…")
        stall_times = 0
        last_count  = 0

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
                last_count  = current_count

        # 主评论爬完，汇报最终主评论数
        _report(progress, "crawl_comments",
                f"主评论爬取完成，共 {len(comments)} 条，开始抓取回复…",
                comment_count=len(comments))

        # ── 统一抓取回复
        total_replies_urls = len(replies_to_fetch)
        logger.info(f"主评论抓取完成，共 {len(comments)} 条，开始抓取 {total_replies_urls} 个评论下的回复...")

        reply_fail_count = 0
        reply_collected = 0

        for idx, url in enumerate(replies_to_fetch):
            try:
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
                                "type": "reply",
                                "mid": r_mid,
                                "text": r_text,
                                "like": r_like,
                                "name": r_name,
                            })
                            reply_collected += 1
                            logger.debug(f"抓取到回复：{r_text[:20]}... (用户: {r_name})")
                else:
                    reply_fail_count += 1
                    logger.debug(f"抓取回复失败: {resp.status}")
            except Exception as e:
                reply_fail_count += 1
                logger.debug(f"请求异常: {e}")

            if total_replies_urls and (
                (idx + 1) % _REPLY_REPORT_EVERY == 0 or idx + 1 == total_replies_urls
            ):
                _report(progress, "crawl_comments",
                        f"正在抓取回复… {idx + 1}/{total_replies_urls}（已收集 {reply_collected} 条回复）",
                        reply_done=idx + 1, reply_total=total_replies_urls,
                        reply_collected=reply_collected)

            time.sleep(0.1)

        if reply_fail_count:
            logger.warning(f"{reply_fail_count} 个回复请求失败，详情见 debug 日志")

        browser.close()

    # 连续任务之间留一个随机间隔，降低被 B 站限流的概率
    delay = random.uniform(*_BETWEEN_TASK_DELAY)
    logger.debug(f"任务间隔等待 {delay:.1f}s")
    time.sleep(delay)

    result = comments if max_count == 0 else comments[:max_count]
    logger.info(f"抓取完成，共收集 {len(result)} 条评论，{reply_collected} 条回复")
    log_event(
        "fetch_comments_done",
        bv_id=bv_id,
        comment_count=len(result),
        reply_count=reply_collected,
        reply_fail_count=reply_fail_count,
    )
    return result
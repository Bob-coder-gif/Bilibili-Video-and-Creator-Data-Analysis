"""
    crawler/get_info_from_browser.py
    获取视频元信息（UP 主 UID / 昵称 / 标题 / cid）与统计数据 stat

    修改时间：
        2026-04-21  用 Playwright 获取视频、UP 主、cid 等信息
        2026-06-21  顺带返回同一次 view 请求里的 stat 字段
        2026-06-22  get_video_info() 改为返回 (video_info, stat)，不再依赖全局变量
===============================
    2026-09-28 修改（解决 HTTP 412 风控导致任务失败）：
    问题：
        原来用裸 requests + 极简 UA（"Mozilla/5.0"）且不带 Cookie 请求 view 接口，
        而且 get_video_info 和 fetch_danmu.get_cid 各请求一次，同一视频重复请求。
        评论抓取后 IP 被风控，view 请求返回 412 HTML 拦截页，.json() 报
        JSONDecodeError，整个任务失败。

    现在 view 接口的数据（videoData）统一由本模块获取和缓存：
        get_video_data(bv_id)  三级获取，按顺序尝试：
            1. 缓存：fetch_comments 打开视频页时从 window.__INITIAL_STATE__.videoData
               读到并写入缓存（正常流程走这一路，零额外请求）。
            2. API 请求：带完整 UA + 登录 Cookie（走 utils.http_utils）。
            3. 浏览器兜底：API 被风控（412）时用 Playwright 打开视频页读取。
           2、3 拿到的数据也写入缓存，同一任务后续再用不会重复请求。
        get_video_info(bv_id)  → (video_info, stat)，返回结构不变
        get_cid(bv_id)         → 第一个分 P 的 cid（给弹幕抓取用）

    缓存有效期 _CACHE_TTL 秒，过期后重新获取，避免拿到过时的 stat 数据。
    视频不存在（-404 等）直接抛 BiliNotFoundError，不做兜底。
===============================
    2026-09-28 清理：
        删除对 cfg.CURRENT_VIDEO_STAT 的全局变量写入（已无读取方，config 中也已删除）；
        浏览器兜底改为使用 config.HEADLESS。
===============================
"""

import os
import threading
import time

from playwright.sync_api import sync_playwright

import config.config as cfg
from crawler.bilibili_state import launch_browser
from utils.http_utils import (
    USER_AGENT,
    bili_get_json,
    parse_bili_body,
    BiliRequestError,
    BiliRiskControlError,
)
from utils.log_utils import get_logger, log_event

logger = get_logger()

VIEW_API = "https://api.bilibili.com/x/web-interface/view"

# 在页面里读取视频信息的 JS（fetch_comments 也用这个，保证两处一致）
JS_READ_VIDEO_DATA = (
    "() => (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.videoData) || null"
)

# 在页面里用浏览器自己的 fetch 请求 view 接口（带页面 Cookie）
_JS_FETCH_VIEW_API = """
async (bvid) => {
    const resp = await fetch(
        "https://api.bilibili.com/x/web-interface/view?bvid=" + bvid,
        { credentials: "include" }
    );
    if (!resp.ok) return { __http_status: resp.status };
    return await resp.json();
}
"""

_STAT_KEYS = ("view", "danmaku", "reply", "favorite", "coin", "share", "like")

# 缓存有效期（秒）。一个任务从开始到抓弹幕通常在这个时间内；
# 过期后重新获取，避免同一视频隔很久再分析时拿到旧的 stat。
_CACHE_TTL = 1800

# bv_id -> (写入时间戳, videoData)
_VIDEO_DATA_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()


def _is_valid_video_data(video_data) -> bool:
    return (
        isinstance(video_data, dict)
        and isinstance(video_data.get("owner"), dict)
        and bool(video_data.get("title"))
    )


def cache_video_data(bv_id: str, video_data) -> bool:
    """缓存 videoData。只缓存字段齐全的数据，返回是否缓存成功。"""
    if not _is_valid_video_data(video_data):
        return False
    with _CACHE_LOCK:
        _VIDEO_DATA_CACHE[bv_id] = (time.time(), video_data)
    return True


def _get_cached(bv_id: str) -> dict | None:
    """取出未过期的缓存；过期的顺手删掉"""
    with _CACHE_LOCK:
        entry = _VIDEO_DATA_CACHE.get(bv_id)
        if entry is None:
            return None
        cached_at, video_data = entry
        if time.time() - cached_at > _CACHE_TTL:
            del _VIDEO_DATA_CACHE[bv_id]
            return None
        return video_data


def _fetch_via_api(bv_id: str) -> dict:
    """方式 2：带完整 UA 和登录 Cookie 请求 view 接口"""
    return bili_get_json(VIEW_API, params={"bvid": bv_id})


def _fetch_via_browser(bv_id: str) -> dict:
    """方式 3：用 Playwright 打开视频页，优先读页面状态，读不到再在页面里 fetch 接口"""
    storage = cfg.STORAGE_PATH if os.path.exists(cfg.STORAGE_PATH) else None

    with sync_playwright() as p:
        browser = launch_browser(p)
        try:
            context = browser.new_context(
                storage_state=storage,
                user_agent=USER_AGENT,
                viewport={"width": 1366, "height": 768},
            )
            page = context.new_page()
            page.goto(
                f"https://www.bilibili.com/video/{bv_id}",
                timeout=60000,
                wait_until="domcontentloaded",
            )

            video_data = page.evaluate(JS_READ_VIDEO_DATA)
            if _is_valid_video_data(video_data):
                return video_data

            logger.debug("页面状态里没有 videoData，改为在页面内请求 view 接口")
            body = page.evaluate(_JS_FETCH_VIEW_API, bv_id)
            if isinstance(body, dict) and body.get("__http_status") == 412:
                raise BiliRiskControlError(
                    "浏览器请求同样被 B 站风控拦截（HTTP 412）", status=412
                )
            if isinstance(body, dict) and "__http_status" in body:
                raise BiliRequestError(
                    f"浏览器请求失败 HTTP {body['__http_status']}",
                    status=body["__http_status"],
                )
            return parse_bili_body(body, VIEW_API)
        finally:
            browser.close()


def get_video_data(bv_id: str) -> tuple[dict, str]:
    """
    获取 B 站 view 接口的 videoData（含 owner/title/stat/cid/pages 等）。

    返回:
        (video_data, source)，source 为 "cache" / "api" / "browser"，用于日志排查

    异常:
        BiliNotFoundError     视频不存在 / 不可见
        BiliRiskControlError  API 和浏览器都被风控
        BiliRequestError      其他请求失败
    """
    video_data = _get_cached(bv_id)
    if video_data is not None:
        return video_data, "cache"

    try:
        video_data = _fetch_via_api(bv_id)
        source = "api"
    except BiliRiskControlError as e:
        logger.warning(f"获取视频信息被风控（{e}），改用浏览器方式重试")
        log_event("video_info_fallback_browser", bv_id=bv_id)
        video_data = _fetch_via_browser(bv_id)
        source = "browser"

    cache_video_data(bv_id, video_data)
    return video_data, source


def get_video_info(bv_id) -> tuple[list, dict]:
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
    video_data, source = get_video_data(bv_id)

    owner = video_data.get("owner") or {}
    video_info = [owner.get("mid"), owner.get("name"), video_data.get("title")]

    raw_stat = video_data.get("stat") or {}
    stat = {k: raw_stat.get(k, 0) for k in _STAT_KEYS}

    log_event("video_info_fetched", bv_id=bv_id, source=source)
    return video_info, stat


def get_cid(bv_id: str) -> int:
    """
    获取视频第一个分 P 的 cid（弹幕接口需要）。
    与 get_video_info 共用同一份缓存，同一任务里不会重复请求。
    """
    video_data, source = get_video_data(bv_id)

    pages = video_data.get("pages") or []
    cid = pages[0].get("cid") if pages else video_data.get("cid")
    if not cid:
        raise BiliRequestError(f"视频信息中没有 cid（bv_id={bv_id}）")

    logger.debug(f"获取到 cid: {cid}（来源: {source}）")
    return cid
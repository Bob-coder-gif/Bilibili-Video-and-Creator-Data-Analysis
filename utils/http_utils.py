"""
utils/http_utils.py

B 站接口请求工具：统一处理 UA/Cookie、状态码检查、风控识别、重试和业务错误码。
项目里所有对 B 站接口的 requests 请求都应该走这里，不要再直接 requests.get。

对外函数：
    bili_get(url, ...)        返回原始 Response，用于非 JSON 接口（如 XML 弹幕）
    bili_get_json(url, ...)   返回 JSON 响应里的 data 字段
    parse_bili_body(body)     校验 JSON 响应体（浏览器内 fetch 的结果也用它校验）
    load_bili_cookies()       从 Playwright 登录态文件读取 B 站 Cookie

异常层级：
    BiliRequestError            通用请求失败
    ├── BiliRiskControlError    被风控拦截（HTTP 412 / 业务码 -412、-352）
    ├── BiliNotFoundError       视频不存在或不可见（业务码 -404、62002、62004）
    └── BiliLoginRequiredError  本地没有登录态文件（2026-09-28 新增）
"""
import json
import os
import time

import requests

import config.config as cfg
from utils.log_utils import get_logger, log_event

logger = get_logger()


class BiliRequestError(Exception):
    """B 站接口请求失败的通用异常"""

    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code = code        # B 站业务码（JSON 里的 code）
        self.status = status    # HTTP 状态码


class BiliRiskControlError(BiliRequestError):
    """被 B 站风控拦截"""


class BiliNotFoundError(BiliRequestError):
    """视频不存在、已删除、不可见或审核中"""


class BiliLoginRequiredError(BiliRequestError):
    """本地没有 B 站登录态，需要先登录"""


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": "https://www.bilibili.com/",
}

# 风控相关业务码
RISK_CODES = {-412, -352}
# 视频不存在 / 不可见相关业务码：-404 啥都木有，62002 稿件不可见，62004 稿件审核中
NOT_FOUND_CODES = {-404, 62002, 62004}


def load_bili_cookies() -> dict | None:
    """从 Playwright 保存的登录态文件里取出 B 站 Cookie，供 requests 使用"""
    path = cfg.STORAGE_PATH
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError) as e:
        logger.debug(f"读取登录态文件失败: {e}")
        return None

    cookies = {
        c["name"]: c["value"]
        for c in state.get("cookies", [])
        if "bilibili.com" in c.get("domain", "")
    }
    return cookies or None


def parse_bili_body(body, url=""):
    """
    校验 B 站接口返回的 JSON 响应体，成功时返回其中的 data 字段。
    requests 请求和浏览器内 fetch 请求都用它来检查，保证判定规则一致。
    """
    if not isinstance(body, dict):
        raise BiliRequestError(f"响应格式异常: {str(body)[:100]!r}")

    code = body.get("code")
    message = body.get("message")

    if code in RISK_CODES:
        log_event("bili_risk_control", url=url, code=code)
        raise BiliRiskControlError(f"业务码 {code}：{message}（风控）", code=code)
    if code in NOT_FOUND_CODES:
        raise BiliNotFoundError(f"业务码 {code}：{message}", code=code)
    if code != 0:
        raise BiliRequestError(f"业务码 {code}：{message}", code=code)

    return body.get("data")


def bili_get(url, params=None, headers=None, cookies=None,
             retries=3, timeout=10, backoff=2.0) -> requests.Response:
    """
    请求 B 站接口，返回 HTTP 200 的原始 Response（不解析内容）。

    - cookies 为 None 时自动从登录态文件加载
    - HTTP 412：立即抛 BiliRiskControlError（重试只会加重风控）
    - 网络错误、5xx：指数退避重试
    - 其他非 200：抛 BiliRequestError
    """
    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    if cookies is None:
        cookies = load_bili_cookies()

    last_error = BiliRequestError("请求失败（未知原因）")

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, headers=merged_headers,
                                cookies=cookies, timeout=timeout)
        except requests.RequestException as e:
            last_error = BiliRequestError(f"网络请求失败: {e}")
            log_event("bili_request_network_error", url=url, attempt=attempt, error=str(e))
            time.sleep(backoff ** attempt)
            continue

        if resp.status_code == 412:
            log_event("bili_risk_control", url=url, status=412)
            raise BiliRiskControlError(
                "HTTP 412：请求被 B 站风控拦截，请稍后再试或更换网络", status=412
            )

        if resp.status_code >= 500:
            last_error = BiliRequestError(f"B 站服务器错误 HTTP {resp.status_code}",
                                          status=resp.status_code)
            log_event("bili_request_server_error", url=url,
                      status=resp.status_code, attempt=attempt)
            time.sleep(backoff ** attempt)
            continue

        if resp.status_code != 200:
            raise BiliRequestError(
                f"HTTP {resp.status_code}，响应开头: {resp.text[:100]!r}",
                status=resp.status_code,
            )

        return resp

    raise last_error


def bili_get_json(url, params=None, headers=None, cookies=None,
                  retries=3, timeout=10, backoff=2.0):
    """
    请求 B 站 JSON 接口，返回响应里的 data 字段（不是整个响应）。
    状态码处理同 bili_get；业务码处理见 parse_bili_body。
    """
    resp = bili_get(url, params=params, headers=headers, cookies=cookies,
                    retries=retries, timeout=timeout, backoff=backoff)
    try:
        body = resp.json()
    except ValueError:
        raise BiliRequestError(
            f"响应不是 JSON（Content-Type: {resp.headers.get('Content-Type')}），"
            f"开头: {resp.text[:100]!r}",
            status=resp.status_code,
        )
    return parse_bili_body(body, url)
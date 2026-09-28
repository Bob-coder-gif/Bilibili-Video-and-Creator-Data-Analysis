"""
诊断当前哪种方式能拿到视频信息。在项目根目录运行：python debug_info.py
"""
import requests

from utils.http_utils import USER_AGENT, load_bili_cookies
from crawler.get_info_from_browser import _fetch_via_browser

BV = "BV1LzrSBNEWi"
URL = "https://api.bilibili.com/x/web-interface/view"
HEADERS = {"User-Agent": USER_AGENT, "Referer": f"https://www.bilibili.com/video/{BV}"}


def test_requests(name, cookies):
    try:
        r = requests.get(URL, params={"bvid": BV}, headers=HEADERS, cookies=cookies, timeout=10)
        if r.status_code == 200:
            print(f"[{name}] HTTP 200, 业务码 code={r.json().get('code')}")
        else:
            print(f"[{name}] HTTP {r.status_code}")
    except Exception as e:
        print(f"[{name}] 异常: {type(e).__name__}: {e}")


# 1. 匿名请求（和旧版 debug_info.py 一样）
test_requests("1.匿名请求", None)

# 2. 带登录态 Cookie 的请求（新代码的 API 路径）
cookies = load_bili_cookies() or {}
print(f"    登录态 Cookie 共 {len(cookies)} 个，"
      f"SESSDATA: {'有' if 'SESSDATA' in cookies else '无'}，"
      f"buvid3: {'有' if 'buvid3' in cookies else '无'}")
test_requests("2.带登录Cookie", cookies or None)

# 3. 浏览器打开视频页读取（新代码的缓存路径 + 兜底路径）
try:
    vd = _fetch_via_browser(BV)
    print(f"[3.浏览器] 成功：标题={vd.get('title')!r}，cid={vd.get('cid')}")
except Exception as e:
    print(f"[3.浏览器] 失败: {type(e).__name__}: {e}")
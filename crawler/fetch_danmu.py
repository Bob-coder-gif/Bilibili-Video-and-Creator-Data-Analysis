"""
fetch_danmu.py

    Fetch danmu from Bilibili

修改时间：
    2026-4-25
-----------------------------
bili弹幕存储结构说明：
    以xml形式存储
    url：https://api.bilibili.com/x/v1/dm/list.so?oid=<cid>
    
<i>
<chatserver>chat.bilibili.com</chatserver>
<chatid>739033648</chatid>
<mission>0</mission>
<maxlimit>500</maxlimit>
<state>0</state>
<real_name>0</real_name>
<source>k-v</source>
<d p="17.38000,1,25,16777215,1777106374,0,ef7be4b9,2097279289006273280,10">测试</d>
</i>

    <d ... >：代表一条弹幕（d 代表 danmaku）。
    ...（引号里的内容）：弹幕的属性，包含了时间、颜色、位置等元数据。
    “测试”：弹幕内容。


| 顺序  | 数值            | 含义        | 详细解读 |
| 第1位 | `17.38000`      | 出现时间    | 这条弹幕会在视频进度条走到 17.38秒 时准时出现。 |
| 第2位 | `1`             | 弹幕类型    | 1: 代表普通滚动弹幕（从右向左飘过）4: 底部固定 5: 顶部固定6: 逆向弹幕7: 高级弹幕
| 第3位 | `25`            | 字体大小    | 标准字号（B站默认通常是25号字）。 |
| 第4位 | `16777215`      | 颜色        | 颜色的十进制代码。`16777215` 换算成十六进制是 `#FFFFFF`，也就是纯白色。 |
| 第5位 | `1777106374`    | 发送时间    | 这是发送者按下“发送”键时的 Unix 时间戳。换算成北京时间大约是 2026年4月24日 17:59:34（也就是昨天傍晚）。 |
| 第6位 | `0`             | 弹幕池      | 0 代表普通池  1 字幕池（通常不可见） 2 特殊池 |
| 第7位 | `ef7be4b9`      | 用户Hash ID | 发送这条弹幕的用户的“代号”。 |
| 第8位 | `2097...280`    | 数据库ID    | 这条弹幕在 B 站数据库里的唯一身份证号。 |
| 第9位 | `10`            | 权重        | 这是一个内部标记，通常用于防刷屏或优先级排序。       

===================================

后续可能会用到的升级：
    当前项目阶段优先使用该版本，后期可升级 protobuf（seg.so）

修改时间：
    2026-4-28
-----------------------------
完成了2026年4月25日的版本，基本功能已完成，后续可以根据需要进行优化和升级。

"""

import requests
import xml.etree.ElementTree as ET
import time
import random


# ── 获取 cid ─────────────────────────────────────────────
def get_cid(bv_id: str) -> int:
    """
    根据 BV 号获取 cid
    """
    url = "https://api.bilibili.com/x/web-interface/view"
    params = {"bvid": bv_id}

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.bilibili.com/"
    }

    try:
        resp = requests.get(url, params=params, headers=headers)
        data = resp.json()

        cid = data["data"]["pages"][0]["cid"]
        return cid

    except Exception as e:
        print(f"[错误] 获取 cid 失败: {e}")
        return None


# ── 解析 XML ─────────────────────────────────────────────
def parse_danmu(xml_text: str) -> list[dict]:
    """
    解析弹幕 XML
    """
    danmus = []

    try:
        root = ET.fromstring(xml_text)

        for d in root.findall("d"):
            try:
                text = d.text
                p = d.attrib.get("p", "").split(",")

                danmu = {
                    "time": float(p[0]),       # 出现时间
                    "type": int(p[1]),         # 类型
                    "size": int(p[2]),         # 字号
                    "color": int(p[3]),        # 颜色
                    "timestamp": int(p[4]),    # 发送时间
                    "text": text.encode("latin-1").decode("utf-8")
                }

                danmus.append(danmu)

            except Exception:
                continue

    except Exception as e:
        print(f"[错误] 解析 XML 失败: {e}")

    return danmus


# ── 主函数 ─────────────────────────────────────────────
def fetch_danmu(bv_id: str) -> list[dict]:
    """
    获取视频全部弹幕

    参数：
        bv_id : 视频BV号

    返回：
        list[dict]
    """

    print(f"\n开始获取弹幕: {bv_id}")

    # 1️获取 cid
    cid = get_cid(bv_id)
    if not cid:
        return []

    print(f"获取到 cid: {cid}")

    # 2 构造 URL
    url = f"https://api.bilibili.com/x/v1/dm/list.so?oid={cid}"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.bilibili.com/"
    }

    # 3️请求弹幕
    try:
        # 随机延迟（防风控）
        time.sleep(random.uniform(0.5, 1.5))

        resp = requests.get(url, headers=headers)

        if resp.status_code != 200:
            print(f"[错误] 请求失败: {resp.status_code}")
            return []

        xml_text = resp.text

    except Exception as e:
        print(f"[错误] 请求弹幕失败: {e}")
        return []

    # 4️解析
    danmus = parse_danmu(xml_text)

    print(f"[INFO] 弹幕获取完成，共 {len(danmus)} 条")

    

    return danmus
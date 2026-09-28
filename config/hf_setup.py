"""
config/hf_setup.py

HuggingFace 网络环境设置（解决国内不挂梯子无法访问 huggingface.co 的问题）

    HF_ENDPOINT    -> 下载源换成国内镜像 https://hf-mirror.com
    HF_HUB_OFFLINE -> 是否只用本地缓存（由 config.HF_OFFLINE 控制）

关键：本模块必须在 import transformers / huggingface_hub / bertopic 之前被 import，
      那些库在 import 时就读取这些环境变量，之后再改无效。
      目前在两处最先 import：app/web.py 第一行、analyzer/bert_analyzer.py 第一行。

2026-09-28 修改：
    原来本模块没有被任何地方 import，实际生效的是 web.py 和 bert_analyzer.py
    顶部各自写死的一份环境变量（强制离线），导致 config.HF_OFFLINE = False 不起作用、
    首次下载模型只能手动改代码。现在两处都改为 import 本模块，离线开关只看 config。
"""

import os

import config.config as cfg


def setup_hf_mirror():
    """设置 HuggingFace 镜像源 + 离线模式"""
    # 用户在外部设置了 HF_ENDPOINT 就尊重用户的设置
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    flag = "1" if getattr(cfg, "HF_OFFLINE", True) else "0"
    os.environ["HF_HUB_OFFLINE"] = flag
    os.environ["TRANSFORMERS_OFFLINE"] = flag


# 被 import 时立即执行
setup_hf_mirror()

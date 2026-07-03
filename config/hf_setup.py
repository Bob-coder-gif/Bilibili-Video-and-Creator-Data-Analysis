"""
config/hf_setup.py

HuggingFace 网络环境设置（解决国内不挂梯子无法访问 huggingface.co 的问题）

为什么需要这个文件：
    transformers / huggingface_hub 默认从 https://huggingface.co 下载和校验模型。
    该域名在国内网络环境下通常无法直接访问（会 ConnectTimeout）。
    本模块通过设置两个环境变量来解决：
      1. HF_ENDPOINT  -> 把下载源换成国内镜像 https://hf-mirror.com
                         （即使需要联网下载，也走国内镜像，不用挂梯子）
      2. HF_HUB_OFFLINE -> 优先使用本地已下载的模型缓存，命中缓存时完全不联网
                         （你之前挂梯子下过的模型会被缓存到本地，秒加载）

关键：本模块必须在 import transformers / huggingface_hub 之前被 import，
      否则那些库启动时已经读过默认地址，再改就晚了。
      因此 bert_analyzer.py 在 import transformers 之前第一行就 import 本模块。

离线开关：
    是否开启"优先离线"由 config.config.HF_OFFLINE 控制：
      - HF_OFFLINE = True （默认）：优先用本地缓存，命中就不联网（最快、最稳）。
                                    但如果本地没有该模型缓存，会直接报错（不会去下载）。
      - HF_OFFLINE = False：允许联网，通过上面的国内镜像下载模型。
                            第一次下载模型、或换了新模型时，临时改成 False 跑一次，
                            下载完成后再改回 True 即可。
"""

import os


def setup_hf_mirror():
    """设置 HuggingFace 镜像源 + 离线模式（从 config 读取离线开关）"""

    # 下载源永远指向国内镜像（即便要联网下载也走国内，不依赖梯子）
    # setdefault：如果用户已经在外部设了 HF_ENDPOINT，就尊重用户的设置，不覆盖
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    # 读取离线开关（默认 True：优先本地缓存）
    # 这里用延迟 import，避免和 config 之间产生 import 循环
    try:
        import config.config as cfg
        offline = getattr(cfg, "HF_OFFLINE", True)
    except Exception:
        # config 读不到时，保守默认为优先离线
        offline = True

    if offline:
        # 1 = 强制离线：只用本地缓存，命中则完全不联网；没缓存会报错
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    else:
        # 允许联网（走上面设置的国内镜像下载）
        os.environ["HF_HUB_OFFLINE"] = "0"
        os.environ["TRANSFORMERS_OFFLINE"] = "0"


# 被 import 时立即执行一次，确保在 transformers 被 import 之前环境变量就绪
setup_hf_mirror()
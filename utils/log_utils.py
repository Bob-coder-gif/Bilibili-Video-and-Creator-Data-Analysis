"""
修改时间：
    2026-06-21
----------------------------------
utils/log_utils.py
统一日志入口：
1. logger.debug/info/warning/error  -> 终端 + 文件（全量），终端默认只显示 INFO 以上
2. log_event(event, **fields)       -> 结构化 JSON，写入 logs/runtime/{date}.jsonl，
                                        不出现在终端，供 grep/jq/前端读取
3. 屏蔽第三方库自己直接往终端写的噪音（不走 logging 模块，level 控制不了）：
   - jieba 的 "Building prefix dict..." 系列 print
   - huggingface_hub 的 "unauthenticated requests" UserWarning
   - transformers / huggingface_hub 的模型下载/加载进度条
================================    
"""
import logging
import json
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("logs")
RUNTIME_DIR = LOG_DIR / "runtime"
DEBUG_LOG_DIR = LOG_DIR / "debug"

_logger = logging.getLogger("bilibili_analyse")
_initialized = False


def setup_logging(verbose: bool = False):
    """
    在 main 入口调用一次。
    verbose=False（默认）：终端只显示 INFO 及以上
    verbose=True （--verbose）：终端显示 DEBUG 及以上（即逐条评论这种细节也打出来）
    文件里始终是全量 DEBUG，不受 verbose 影响。
    """
    global _initialized
    if _initialized:
        return _logger

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)

    _logger.setLevel(logging.DEBUG)
    _logger.handlers.clear()

    # 终端 handler：默认 INFO，--verbose 时 DEBUG
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(console_handler)

    # 文件 handler：全量 DEBUG，永久落盘，按天分文件
    date_str = datetime.now().strftime("%Y%m%d")
    file_handler = logging.FileHandler(
        DEBUG_LOG_DIR / f"{date_str}.log", encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    _logger.addHandler(file_handler)

    # 静音第三方库走 logging 模块的输出，只保留 WARNING 以上
    for noisy in ("transformers", "jieba", "urllib3", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _silence_third_party_noise(verbose)

    _initialized = True
    return _logger


def _silence_third_party_noise(verbose: bool):
    """
    屏蔽不走 logging 模块、logger.setLevel 管不到的第三方噪音。
    这些库直接 print / warnings.warn / 自带 tqdm 进度条往终端写，
    必须用各自的专用开关关掉。
    """
    # jieba "Building prefix dict from the default dictionary..."
    # jieba 较新版本可以用 setLogLevel 控制
    try:
        import jieba
        jieba.setLogLevel(logging.WARNING)
    except Exception:
        pass

    # huggingface_hub 的 "You are sending unauthenticated requests..." 是
    # warnings.warn(UserWarning) 发的，不走 logging，要单独过滤
    warnings.filterwarnings(
        "ignore",
        message=".*unauthenticated requests.*",
        category=UserWarning,
    )

    # transformers / huggingface_hub 的模型下载、权重加载进度条
    # （"Loading weights: 100%|..." 这种）：用专用环境变量 + API 关掉
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    try:
        from huggingface_hub.utils import disable_progress_bars
        disable_progress_bars()
    except Exception:
        pass
    try:
        from transformers.utils import logging as hf_logging
        hf_logging.set_verbosity_error()
    except Exception:
        pass

    # --verbose 时把这些都放回来，方便排查模型加载问题
    if verbose:
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "0"
        try:
            from huggingface_hub.utils import enable_progress_bars
            enable_progress_bars()
        except Exception:
            pass


def get_logger():
    if not _initialized:
        setup_logging()
    return _logger


def log_event(event: str, bv_id: str = None, **fields):
    """
    写一条结构化 JSON 到 logs/runtime/{date}.jsonl，不打印到终端。
    例：
        log_event("fetch_comments_done", bv_id=bv_id, count=12, path=str(p))
    """
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        **({"bv_id": bv_id} if bv_id else {}),
        **fields,
    }
    with open(RUNTIME_DIR / f"{date_str}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
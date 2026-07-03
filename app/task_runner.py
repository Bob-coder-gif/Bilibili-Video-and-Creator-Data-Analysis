"""
app/task_runner.py

真排队版任务队列（queue.Queue + 单 worker 线程，纯 Python 标准库，不依赖 Redis）

为什么这么设计：
    之前的版本是"来一个任务就开一个新线程，全部并发跑"。但本项目的爬虫用真实
    浏览器（Playwright）爬 B 站，多个任务并发 = 多个浏览器同时用同一套登录态、
    同一个 IP 高频请求 B 站，这种行为模式更容易触发 B 站风控；BERT 也会互相抢
    CPU。所以改为：

    所有任务进一个 queue.Queue，后台只有 1 个 worker 线程，一个一个取出来串行跑。
    同一时刻只有一路在爬 B 站，行为最像正常用户，最不容易被风控；任务多时自动排队。

    用 1 个 worker（而非多个）是刻意的：单路串行既避免资源争抢，也降低风控风险。

局限（单机自用足够，但要知道）：
    - 任务状态 / 队列存在内存里，程序一重启就全部丢失（排队中和正在跑的都会中断）
    - 不适合多进程 / 多机部署；那种场景才需要 Redis + RQ
"""

from __future__ import annotations

import queue
import threading
import traceback
import uuid
from datetime import datetime

from utils.log_utils import get_logger, log_event

logger = get_logger()

# ---- 任务表 & 队列（都在内存里，线程安全）----
_TASKS: dict[str, dict] = {}        # task_id -> 任务状态 dict
_LOCK = threading.Lock()            # 保护 _TASKS 的读写
_QUEUE: "queue.Queue[str]" = queue.Queue()   # 待处理的 task_id 队列（FIFO）
_ORDER: list[str] = []              # 已提交任务的顺序（用于算"前面还有几个"）
_worker_started = False
_worker_lock = threading.Lock()

# worker 数量固定为 1：单路串行爬取，避免并发触发 B 站风控、避免资源争抢
_NUM_WORKERS = 1


# ---- 任务阶段常量（前端按这个显示文案）----
STAGE_QUEUED = "queued"
STAGE_CRAWL_COMMENTS = "crawl_comments"
STAGE_CRAWL_DANMU = "crawl_danmu"
STAGE_VISUALIZE = "visualize"
STAGE_SENTIMENT = "sentiment"
STAGE_ANALYSIS = "analysis"
STAGE_DONE = "done"
STAGE_ERROR = "error"
STAGE_CANCELLED = "cancelled"

STAGE_TEXT = {
    STAGE_QUEUED: "排队中…",
    STAGE_CRAWL_COMMENTS: "正在爬取评论…",
    STAGE_CRAWL_DANMU: "正在爬取弹幕…",
    STAGE_VISUALIZE: "正在生成可视化图表…",
    STAGE_SENTIMENT: "正在进行情绪分析…",
    STAGE_ANALYSIS: "正在统计趋势 / 预警 / 话题聚类…",
    STAGE_DONE: "完成",
    STAGE_ERROR: "出错了",
    STAGE_CANCELLED: "已取消",
}


def _update(task_id: str, stage: str, message: str = "", **extra):
    """更新某个任务的进度（线程安全）"""
    with _LOCK:
        t = _TASKS.get(task_id)
        if t is None:
            return
        t["stage"] = stage
        t["stage_text"] = message or STAGE_TEXT.get(stage, stage)
        t["updated_at"] = datetime.now().strftime("%H:%M:%S")
        for k, v in extra.items():
            t[k] = v


def get_task(task_id: str) -> dict | None:
    """查询单个任务当前状态（前端轮询用）。会附带算出"前面还有几个在排队"。"""
    with _LOCK:
        t = _TASKS.get(task_id)
        if t is None:
            return None
        result = dict(t)

    # 如果还在排队，算出前面有多少个未完成的任务（不持锁算，减少锁占用）
    if result.get("stage") == STAGE_QUEUED:
        result["ahead"] = _count_ahead(task_id)
    else:
        result["ahead"] = 0
    return result


def _count_ahead(task_id: str) -> int:
    """这个任务前面还有几个未完成（排队中或正在跑）的任务"""
    with _LOCK:
        try:
            idx = _ORDER.index(task_id)
        except ValueError:
            return 0
        ahead = 0
        for other in _ORDER[:idx]:
            ot = _TASKS.get(other)
            if ot and ot.get("ok") is None:   # 还没结束（既不成功也不失败）
                ahead += 1
        return ahead


def get_queue_overview() -> dict:
    """
    队列概览（前端显示用）：当前正在跑的任务 + 还在排队的任务列表。
    """
    with _LOCK:
        running = None
        waiting = []
        for tid in _ORDER:
            t = _TASKS.get(tid)
            if not t:
                continue
            stage = t.get("stage")
            if t.get("ok") is None and stage != STAGE_QUEUED:
                # 既没结束、又不是排队中 → 正在处理
                running = {
                    "task_id": tid, "bv_id": t.get("bv_id"),
                    "stage_text": t.get("stage_text", ""),
                }
            elif stage == STAGE_QUEUED:
                waiting.append({"task_id": tid, "bv_id": t.get("bv_id")})
    return {"running": running, "waiting": waiting, "waiting_count": len(waiting)}


def cancel_task(task_id: str) -> dict:
    """
    取消一个【排队中】的任务。

    实现说明：task_id 已经放进 queue.Queue 了，而 Queue 不支持从中间删元素，
    所以这里用"标记取消"的办法——把任务状态改成 cancelled。worker 之后从队列里
    取到它时，会发现已取消、直接跳过不执行（见 _worker_loop）。

    安全限制：只能取消【排队中(queued)】的任务。正在跑的任务不能中途强杀
    （会留下半个浏览器/半个文件），所以正在跑的不允许取消。

    返回: {"ok": bool, "reason": str}
    """
    with _LOCK:
        t = _TASKS.get(task_id)
        if t is None:
            return {"ok": False, "reason": "任务不存在"}
        if t.get("stage") != STAGE_QUEUED:
            # 已经在跑、已完成、已失败、已取消的，都不能再取消
            return {"ok": False, "reason": "该任务不在排队中，无法取消"}
        # 标记为已取消（ok=False 表示已结束；worker 取到会跳过）
        t["stage"] = STAGE_CANCELLED
        t["stage_text"] = STAGE_TEXT[STAGE_CANCELLED]
        t["ok"] = False
        t["error"] = "已取消"
    log_event("task_cancelled", task_id=task_id)
    return {"ok": True, "reason": "已取消"}


def clear_queue() -> dict:
    """
    清空队列：取消所有【排队中】的任务。正在跑的那个不动，让它跑完。
    返回: {"ok": True, "cancelled": 被取消的任务数}
    """
    cancelled = 0
    with _LOCK:
        for tid in _ORDER:
            t = _TASKS.get(tid)
            if t and t.get("stage") == STAGE_QUEUED:
                t["stage"] = STAGE_CANCELLED
                t["stage_text"] = STAGE_TEXT[STAGE_CANCELLED]
                t["ok"] = False
                t["error"] = "已取消"
                cancelled += 1
    log_event("queue_cleared", cancelled=cancelled)
    return {"ok": True, "cancelled": cancelled}


def submit_task(bv_id: str) -> str:
    """提交一个分析任务：放进队列，立刻返回 task_id。真正的执行由后台 worker 串行处理。"""
    _ensure_worker()

    task_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _TASKS[task_id] = {
            "task_id": task_id,
            "bv_id": bv_id,
            "stage": STAGE_QUEUED,
            "stage_text": STAGE_TEXT[STAGE_QUEUED],
            "created_at": datetime.now().strftime("%H:%M:%S"),
            "updated_at": datetime.now().strftime("%H:%M:%S"),
            "ok": None,        # None=未结束, True=成功, False=失败
            "error": None,
            "result": None,
        }
        _ORDER.append(task_id)

    _QUEUE.put(task_id)
    log_event("task_submitted", task_id=task_id, bv_id=bv_id)
    return task_id


def _ensure_worker():
    """懒启动后台 worker 线程（只启动一次）"""
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        for i in range(_NUM_WORKERS):
            th = threading.Thread(target=_worker_loop, name=f"task-worker-{i}", daemon=True)
            th.start()
        _worker_started = True
        logger.debug(f"[task_runner] 已启动 {_NUM_WORKERS} 个后台 worker")


def _make_progress_callback(task_id: str):
    """生成传给 pipeline 的进度回调：pipeline 在关键节点调用它汇报进度"""
    def callback(stage: str, message: str = "", **extra):
        _update(task_id, stage, message, **extra)
    return callback


def _worker_loop():
    """worker 主循环：不断从队列取任务、串行执行"""
    while True:
        task_id = _QUEUE.get()        # 队列空时在这里阻塞等待，不占 CPU
        try:
            # 取出来先检查是否已被取消（cancel_task / clear_queue 会标记 cancelled）。
            # 因为 queue.Queue 不能从中间删元素，被取消的任务仍会被取出，
            # 这里发现已取消就直接跳过，不执行。
            with _LOCK:
                t = _TASKS.get(task_id)
                cancelled = (t is None) or (t.get("stage") == STAGE_CANCELLED)
            if cancelled:
                logger.debug(f"[task_runner] 任务 {task_id} 已取消，跳过执行")
                continue

            bv_id = _TASKS.get(task_id, {}).get("bv_id")
            if bv_id:
                _run_one(task_id, bv_id)
        except Exception as e:
            # worker 自身的意外错误（理论上 _run_one 已兜底，这里再保一层）
            logger.error(f"[task_runner] worker 处理任务 {task_id} 时异常: {e}")
            _update(task_id, STAGE_ERROR, message="任务执行异常", ok=False, error="任务执行异常")
        finally:
            _QUEUE.task_done()


def _run_one(task_id: str, bv_id: str):
    """实际执行一个任务：依次跑三个 pipeline，全程更新进度"""
    # 延迟 import，避免循环依赖
    import pipeline.crawler_pipeline as cp
    import pipeline.sentiment_pipeline as sp
    import pipeline.pipeline_data_analysis as dp

    progress = _make_progress_callback(task_id)

    try:
        progress(STAGE_CRAWL_COMMENTS)
        task = cp.crawler_pipeline(bv_id, progress=progress)

        progress(STAGE_SENTIMENT)
        task = sp.sentiment_pipeline(task, progress=progress)

        progress(STAGE_ANALYSIS)
        task = dp.pipeline_data_analysis(task, progress=progress)

        vsr = task.get("video_stats_result") or {}
        result = {
            "bv_id": task.get("bv_id"),
            "video_info": task.get("video_info"),
            "report_path": task.get("report_path"),
            "trend_image_path": vsr.get("trend_image_path"),
            "history_point_count": vsr.get("point_count"),
        }
        _update(task_id, STAGE_DONE, ok=True, result=result)
        log_event("task_done", task_id=task_id, bv_id=bv_id)

    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        logger.error(f"任务 {task_id} 失败: {err}\n{traceback.format_exc()}")
        log_event("task_failed", task_id=task_id, bv_id=bv_id, error=err)
        _update(task_id, STAGE_ERROR, message="分析失败，请确认 BV 号或稍后重试",
                ok=False, error="分析失败，请确认 BV 号是否正确，或稍后重试")
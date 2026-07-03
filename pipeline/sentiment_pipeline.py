"""
sentiment_pipeline.py
Bilibili 评论 / 弹幕情绪分析 —— 主入口

修改时间：
    2026-06-22
----------------------------------
重构说明（第二阶段第一步）：
    sentiment_pipeline(task) 接收上一步 crawler_pipeline 返回的 task 字典，
    优先用 task 里的 bv_id / video_info / comments_path / danmaku_path，
    缺字段时退回 argparse + load_meta 反查（兼容命令行单独调试）。

修改时间：
    2026-06-27
----------------------------------
    1. time_str：从 task 取本次任务统一时间目录名，传给所有 save_* 调用，
       保证同一次任务的全部产物落在同一个 {time_str}/ 目录下。
    2. 新增可选 progress 回调：在情绪分析 / 关键词 / 生成报告等节点汇报进度，
       供网页后台任务实时显示。progress=None 时跳过（命令行单独跑即为 None）。

用法（命令行单独测试）:
    python sentiment_pipeline.py
    python sentiment_pipeline.py --comments comments.json --danmaku danmaku.json --backend bert
"""

import argparse
import os
import json
import pandas as pd

import config.config as cfg
from utils.loader   import load_comments, load_danmaku, load_meta
from utils.cleaner  import clean_dataframe
from analyzer.keyword_extractor import extract_keywords, word_frequency
from visualization.report import generate_report
from pathlib import Path
from utils.file_utils import save_results, save_word_freq
from utils.log_utils import get_logger, log_event

logger = get_logger()


def _report(progress, stage, message="", **extra):
    """安全调用进度回调：progress 为 None 时什么也不做"""
    if progress is not None:
        progress(stage, message, **extra)


# ------------------------------------------------------------------ CLI ------

def parse_args():
    p = argparse.ArgumentParser(description="Bilibili 评论情绪分析")
    p.add_argument("--comments", default=cfg.COMMENTS_FILE)
    p.add_argument("--danmaku",  default=cfg.DANMAKU_FILE)
    p.add_argument("--backend",  default=cfg.SENTIMENT_BACKEND, choices=["bert"])
    p.add_argument("--output",   default=cfg.OUTPUT_DIR)
    return p.parse_args()


# ------------------------------------------------------------------ pipeline --

def run_sentiment(df, backend="bert"):
    from analyzer.bert_analyzer import analyze as bert_analyze
    df = bert_analyze(df, cfg)
    return df, "bert_label"


def _ensure_data_files(comments_path: Path, danmaku_path: Path):
    """文件不存在时创建空结构，防止报错（结构需与 loader._load_json 的判断逻辑一致：
    评论用 dict 包裹的 "comments"，弹幕用 list 包裹的 "danmus"）"""
    if not comments_path.exists():
        logger.warning(f"评论文件不存在: {comments_path}")
        log_event("comments_file_missing", path=str(comments_path))
        comments_path.parent.mkdir(parents=True, exist_ok=True)
        with open(comments_path, 'w', encoding='utf-8') as f:
            json.dump({"comments": {}}, f, ensure_ascii=False)

    if not danmaku_path.exists():
        logger.warning(f"弹幕文件不存在: {danmaku_path}")
        log_event("danmaku_file_missing", path=str(danmaku_path))
        danmaku_path.parent.mkdir(parents=True, exist_ok=True)
        with open(danmaku_path, 'w', encoding='utf-8') as f:
            json.dump({"danmus": []}, f, ensure_ascii=False)


# ---------------------------------------------------------------------- main --

def sentiment_pipeline(task: dict | None = None, progress=None) -> dict:
    """
    情绪分析管道入口。

    参数:
        task: 上一步 crawler_pipeline() 返回的 task 字典，期望包含
              bv_id / video_info / comments_path / danmaku_path / time_str。
              传 None 或缺字段时，退回旧的 argparse + load_meta 反查逻辑。
        progress: 可选进度回调；None 时不汇报（命令行单独跑时即为 None）。

    返回:
        更新后的 task 字典，补充情绪分析阶段产出 + 给下游分析阶段准备的数据。
    """
    if task is None:
        task = {}

    # argparse 只在 task 没提供对应字段时才需要，避免在网页后端等没有
    # 正常命令行参数（sys.argv）的环境下，无条件解析导致报错或拿到意外值
    need_args = not all(k in task for k in ("comments_path", "danmaku_path", "backend", "output"))
    args = parse_args() if need_args else None

    backend = task.get("backend", args.backend if args else cfg.SENTIMENT_BACKEND)
    log_event("sentiment_pipeline_start", backend=backend)

    output_dir = task.get("output", args.output if args else cfg.OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)

    comments_path = Path(task.get("comments_path", args.comments if args else cfg.COMMENTS_FILE))
    danmaku_path = Path(task.get("danmaku_path", args.danmaku if args else cfg.DANMAKU_FILE))

    # 本次任务统一的时间目录名（来自 crawler_pipeline），传给后面所有 save_* 调用。
    # 没有就交给各 save 函数自己生成（向后兼容）。
    time_str = task.get("time_str")

    _ensure_data_files(comments_path, danmaku_path)

    # 优先用 task 里传来的 bv_id / video_info（来自 crawler_pipeline 这次抓取），
    # 没有的话才退回从文件里反查元信息（兼容单独调试场景）
    bv_id = task.get("bv_id")
    video_info = task.get("video_info")

    if not bv_id or not video_info:
        meta = load_meta(str(comments_path))
        if not meta.get("bv_id"):
            meta_dm = load_meta(str(danmaku_path))
            for k, v in meta_dm.items():
                if v and not meta.get(k):
                    meta[k] = v

        bv_id = meta.get("bv_id") or "unknown_bv"
        video_info = [
            meta.get("uid", ""),
            meta.get("uname") or "unknown_uploader",
            meta.get("title") or "unknown_title",
        ]

    # 1. 加载
    comments_raw = load_comments(str(comments_path), cfg)
    danmaku_raw = load_danmaku(str(danmaku_path), cfg)
    logger.debug(f"[loader] 加载评论 {len(comments_raw)} 条")
    logger.debug(f"[loader] 加载弹幕 {len(danmaku_raw)} 条")

    # 2. 清洗
    comments_df = clean_dataframe(comments_raw) if not comments_raw.empty else comments_raw
    danmaku_df  = clean_dataframe(danmaku_raw)  if not danmaku_raw.empty  else danmaku_raw
    logger.debug(f"[cleaner] 清洗后保留 {len(comments_df)} 条")
    logger.debug(f"[cleaner] 清洗后保留 {len(danmaku_df)} 条")
    log_event(
        "sentiment_data_loaded",
        bv_id=bv_id,
        comments_raw=len(comments_raw),
        danmaku_raw=len(danmaku_raw),
        comments_clean=len(comments_df),
        danmaku_clean=len(danmaku_df),
    )

    # 3. 情绪分析（这步最慢，汇报待分析条数）
    n = (len(comments_df) if not comments_df.empty else 0) + \
        (len(danmaku_df) if not danmaku_df.empty else 0)
    _report(progress, "sentiment", f"正在进行情绪分析（约 {n} 条文本，首次加载模型较慢）…")

    label_col = "bert_label"   # 默认，后续可能被覆盖
    if not comments_df.empty:
        comments_df, label_col = run_sentiment(comments_df, backend)
    if not danmaku_df.empty:
        danmaku_df, label_col = run_sentiment(danmaku_df, backend)

    # 4. 保存带标注的 JSON（保存到 data/report/{uname}/{title}/{bv_id}/{time_str}/ 下）
    if cfg.SAVE_ANNOTATED_JSON:
        if not comments_df.empty:
            comments_save_path = save_results(comments_df, "comments", bv_id, video_info, time_str=time_str)
            logger.debug(f"[save] comments 已保存: {comments_save_path}")
            log_event("comments_annotated_saved", bv_id=bv_id, path=str(comments_save_path))
        if not danmaku_df.empty:
            danmaku_save_path = save_results(danmaku_df, "danmaku", bv_id, video_info, time_str=time_str)
            logger.debug(f"[save] danmaku 已保存: {danmaku_save_path}")
            log_event("danmaku_annotated_saved", bv_id=bv_id, path=str(danmaku_save_path))

    # 5. 关键词提取（基于评论，弹幕太短效果差）
    _report(progress, "sentiment", "正在提取关键词…")
    kw_src = comments_df if not comments_df.empty else danmaku_df
    keywords_all = []
    keywords_pos = []
    keywords_neg = []
    if not kw_src.empty:
        keywords_all = extract_keywords(kw_src, cfg)
        if label_col in kw_src.columns:
            keywords_pos = extract_keywords(kw_src, cfg, label_filter="正向", label_col=label_col)
            keywords_neg = extract_keywords(kw_src, cfg, label_filter="负向", label_col=label_col)
        # 保存词频
        freq = word_frequency(kw_src, cfg)
        freq_path = save_word_freq(freq, bv_id, video_info, time_str=time_str)
        logger.debug(f"词频统计已保存: {freq_path}")
        log_event("word_freq_saved", bv_id=bv_id, path=str(freq_path), word_count=len(freq))

    # 6. 生成情绪分析报告（JSON 格式）
    # 保存路径由 file_utils.save_report 自动拼接为:
    #   data/report/{uname}/{title}/{bv_id}/{time_str}/report.json
    _report(progress, "sentiment", "正在生成情绪分析报告…")
    report_path = generate_report(
        comments_df=comments_df,
        danmaku_df=danmaku_df,
        label_col=label_col,
        keywords_all=keywords_all,
        keywords_pos=keywords_pos,
        keywords_neg=keywords_neg,
        bv_id=bv_id,
        video_info=video_info,
        time_str=time_str,
    )
    log_event("sentiment_report_saved", bv_id=bv_id, report_path=str(report_path))

    logger.info("✅ 情绪分析完成！")
    logger.info(f"   报告: {report_path}")
    logger.info(f"   结果目录: {output_dir}/")

    # ---- 为下游"分析阶段"（话题聚类 / 预警）准备数据 ----
    # 话题聚类需要清洗后的评论文本（+情绪标签），预警需要情绪 summary。
    # 这些数据现在内存里已经有了，直接放进 task 传下去，避免下游重新读盘。

    # 评论的清洗后文本 + 情绪标签（话题聚类用；评论为空则给空列表）
    if not comments_df.empty and "text_clean" in comments_df.columns:
        task["comment_texts"] = comments_df["text_clean"].dropna().tolist()
        if label_col in comments_df.columns:
            mask = comments_df["text_clean"].notna()
            task["comment_labels"] = comments_df.loc[mask, label_col].tolist()
        else:
            task["comment_labels"] = None
    else:
        task["comment_texts"] = []
        task["comment_labels"] = None

    # 情绪 summary（预警用）：统计评论的情绪标签计数 {"正向":n,"中性":n,"负向":n}
    if not comments_df.empty and label_col in comments_df.columns:
        task["sentiment_summary"] = comments_df[label_col].value_counts().to_dict()
    else:
        task["sentiment_summary"] = {}

    # 原有字段
    task["bv_id"] = bv_id
    task["video_info"] = video_info
    task["label_col"] = label_col
    task["report_path"] = str(report_path)
    return task


# ------------------------------------------------------------------ CLI ----

if __name__ == "__main__":
    sentiment_pipeline(None)
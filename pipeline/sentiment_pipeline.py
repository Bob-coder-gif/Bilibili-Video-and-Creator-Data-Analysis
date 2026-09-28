"""
pipeline/sentiment_pipeline.py
情绪分析阶段：加载 → 清洗 → BERT 情绪分析 → 关键词 → 生成报告

修改时间：
    2026-06-22  改为接收 crawler_pipeline 返回的 task 字典
    2026-06-27  使用 task 中统一的 time_str；新增可选 progress 回调

修改时间：
    2026-09-28
----------------------------------
    1. 删除 argparse 命令行参数、__main__ 入口、load_meta 反查、_ensure_data_files。
       隐藏问题：原来判断"是否需要解析命令行"时检查 task 里有没有 backend / output，
       而 crawler_pipeline 从不提供这两个字段，所以网页后台线程里每次都会执行
       argparse.parse_args()——一旦启动服务时带了额外参数，worker 线程会直接 SystemExit。
    2. 删除 backend 参数（只有 BERT 一种后端）。
    3. 情绪分析前增加"评论和弹幕都为空"的明确提示。
"""

from pathlib import Path

import config.config as cfg
from analyzer.keyword_extractor import extract_keywords, word_frequency
from utils.cleaner import clean_dataframe
from utils.file_utils import save_results, save_word_freq
from utils.loader import load_comments, load_danmaku
from utils.log_utils import get_logger, log_event
from visualization.report import generate_report

logger = get_logger()

LABEL_COL = "bert_label"


def _report(progress, stage, message="", **extra):
    """安全调用进度回调：progress 为 None 时什么也不做"""
    if progress is not None:
        progress(stage, message, **extra)


def _analyze(df):
    """清洗 + BERT 情绪分析；空表原样返回"""
    if df.empty:
        return df
    df = clean_dataframe(df)
    if df.empty:
        return df
    from analyzer.bert_analyzer import analyze as bert_analyze   # 延迟 import：加载 torch 较慢
    return bert_analyze(df, cfg)


def sentiment_pipeline(task: dict, progress=None) -> dict:
    """
    情绪分析阶段入口。

    需要的 task 字段（由 crawler_pipeline 写入）：
        bv_id / video_info / comments_path / danmaku_path / time_str

    新增的 task 字段：
        report_path       情绪报告路径
        label_col         情绪标签列名
        comment_texts     清洗后的评论文本（话题聚类用）
        comment_labels    对应的情绪标签（话题聚类用）
        sentiment_summary 评论情绪计数 {"正向": n, "中性": n, "负向": n}（预警用）
    """
    bv_id = task["bv_id"]
    video_info = task["video_info"]
    time_str = task.get("time_str")
    log_event("sentiment_pipeline_start", bv_id=bv_id)

    # 1. 加载
    comments_raw = load_comments(str(Path(task["comments_path"])), cfg)
    danmaku_raw = load_danmaku(str(Path(task["danmaku_path"])), cfg)
    if comments_raw.empty and danmaku_raw.empty:
        logger.warning("评论和弹幕都为空，情绪分析结果将全部为 0")

    # 2~3. 清洗 + 情绪分析（最慢的一步）
    n = len(comments_raw) + len(danmaku_raw)
    _report(progress, "sentiment", f"正在进行情绪分析（约 {n} 条文本，首次加载模型较慢）…")
    comments_df = _analyze(comments_raw)
    danmaku_df = _analyze(danmaku_raw)
    log_event(
        "sentiment_data_loaded",
        bv_id=bv_id,
        comments_raw=len(comments_raw), danmaku_raw=len(danmaku_raw),
        comments_clean=len(comments_df), danmaku_clean=len(danmaku_df),
    )

    # 4. 保存带标注的 JSON
    if cfg.SAVE_ANNOTATED_JSON:
        for name, df in (("comments", comments_df), ("danmaku", danmaku_df)):
            if not df.empty:
                path = save_results(df, name, bv_id, video_info, time_str=time_str)
                log_event(f"{name}_annotated_saved", bv_id=bv_id, path=str(path))

    # 5. 关键词（优先用评论，弹幕太短效果差）
    _report(progress, "sentiment", "正在提取关键词…")
    kw_src = comments_df if not comments_df.empty else danmaku_df
    keywords_all, keywords_pos, keywords_neg = [], [], []
    if not kw_src.empty:
        keywords_all = extract_keywords(kw_src, cfg)
        keywords_pos = extract_keywords(kw_src, cfg, label_filter="正向", label_col=LABEL_COL)
        keywords_neg = extract_keywords(kw_src, cfg, label_filter="负向", label_col=LABEL_COL)
        freq = word_frequency(kw_src, cfg)
        freq_path = save_word_freq(freq, bv_id, video_info, time_str=time_str)
        log_event("word_freq_saved", bv_id=bv_id, path=str(freq_path), word_count=len(freq))

    # 6. 情绪分析报告
    _report(progress, "sentiment", "正在生成情绪分析报告…")
    report_path = generate_report(
        comments_df=comments_df,
        danmaku_df=danmaku_df,
        label_col=LABEL_COL,
        keywords_all=keywords_all,
        keywords_pos=keywords_pos,
        keywords_neg=keywords_neg,
        bv_id=bv_id,
        video_info=video_info,
        time_str=time_str,
    )
    log_event("sentiment_report_saved", bv_id=bv_id, report_path=str(report_path))
    logger.info(f"✅ 情绪分析完成！报告: {report_path}")

    # 7. 给下游"分析阶段"准备数据（内存里已有，避免重新读盘）
    #    clean_dataframe 已过滤掉空文本，text_clean 不会有缺失值，文本和标签一一对应
    if not comments_df.empty:
        task["comment_texts"] = comments_df["text_clean"].tolist()
        task["comment_labels"] = comments_df[LABEL_COL].tolist()
        task["sentiment_summary"] = {k: int(v) for k, v in comments_df[LABEL_COL].value_counts().items()}
    else:
        task["comment_texts"] = []
        task["comment_labels"] = None
        task["sentiment_summary"] = {}

    task["label_col"] = LABEL_COL
    task["report_path"] = str(report_path)
    return task

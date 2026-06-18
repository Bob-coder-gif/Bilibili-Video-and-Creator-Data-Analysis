"""
sentiment_pipeline.py
Bilibili 评论 / 弹幕情绪分析 —— 主入口
用法:
    python sentiment_pipeline.py
    python sentiment_pipeline.py --comments comments.json --danmaku danmaku.json --backend snownlp
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

# ------------------------------------------------------------------ CLI ------

def parse_args():
    p = argparse.ArgumentParser(description="Bilibili 评论情绪分析")
    p.add_argument("--comments", default=cfg.COMMENTS_FILE)
    p.add_argument("--danmaku",  default=cfg.DANMAKU_FILE)
    p.add_argument("--backend",  default=cfg.SENTIMENT_BACKEND,
                   choices=["snownlp", "bert", "both"])
    p.add_argument("--output",   default=cfg.OUTPUT_DIR)
    return p.parse_args()

# ------------------------------------------------------------------ pipeline --

def run_sentiment(df: pd.DataFrame, backend: str) -> tuple[pd.DataFrame, str]:
    """对 df 运行情绪分析，返回 (annotated_df, label_column_name)"""
    if backend in ("snownlp", "both"):
        from analyzer.snownlp_analyzer import analyze as snow_analyze
        df = snow_analyze(df, cfg)

    if backend in ("bert", "both"):
        from analyzer.bert_analyzer import analyze as bert_analyze
        df = bert_analyze(df, cfg)

    # 决定"主"标签列
    if backend == "both":
        # 当两者都有时，BERT 优先
        label_col = "bert_label"
    elif backend == "bert":
        label_col = "bert_label"
    else:
        label_col = "snownlp_label"

    return df, label_col


# ---------------------------------------------------------------------- main --

def sentiment_pipeline():
    args = parse_args()

    os.makedirs(args.output, exist_ok=True)

    comments_path = Path(args.comments)
    danmaku_path = Path(args.danmaku)

    # 文件不存在时创建空结构，防止报错（结构需与 loader._load_json 的判断逻辑一致：
    # 评论用 dict 包裹的 "comments"，弹幕用 list 包裹的 "danmus"）
    if not comments_path.exists():
        print(f"[警告] 评论文件不存在: {comments_path}")
        comments_path.parent.mkdir(parents=True, exist_ok=True)
        with open(comments_path, 'w', encoding='utf-8') as f:
            json.dump({"comments": {}}, f, ensure_ascii=False)

    if not danmaku_path.exists():
        print(f"[警告] 弹幕文件不存在: {danmaku_path}")
        danmaku_path.parent.mkdir(parents=True, exist_ok=True)
        with open(danmaku_path, 'w', encoding='utf-8') as f:
            json.dump({"danmus": []}, f, ensure_ascii=False)

    # 提前读元信息（uname / title / bv_id），save_results 和 generate_report 都要用
    # 从已加载好的评论文件里读；评论文件没有元信息（比如空结构兜底）就用弹幕文件兜底
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

    # 2. 清洗
    comments_df = clean_dataframe(comments_raw) if not comments_raw.empty else comments_raw
    danmaku_df  = clean_dataframe(danmaku_raw)  if not danmaku_raw.empty  else danmaku_raw

    # 3. 情绪分析
    label_col = "snownlp_label"   # 默认，后续可能被覆盖
    if not comments_df.empty:
        comments_df, label_col = run_sentiment(comments_df, args.backend)
    if not danmaku_df.empty:
        danmaku_df, label_col = run_sentiment(danmaku_df, args.backend)

    # 4. 保存带标注的 JSON（保存到 data/report/{uname}/{title}/ 下）
    if cfg.SAVE_ANNOTATED_JSON:
        if not comments_df.empty:
            save_results(comments_df, "comments", bv_id, video_info)
        if not danmaku_df.empty:
            save_results(danmaku_df, "danmaku", bv_id, video_info)

    # 5. 关键词提取（基于评论，弹幕太短效果差）
    kw_src = comments_df if not comments_df.empty else danmaku_df
    keywords_all = []
    keywords_pos = []
    keywords_neg = []
    if not kw_src.empty:
        keywords_all = extract_keywords(kw_src, cfg)
        if label_col in kw_src.columns:
            keywords_pos = extract_keywords(kw_src, cfg, label_filter="正向")
            keywords_neg = extract_keywords(kw_src, cfg, label_filter="负向")
        # 保存词频
        freq = word_frequency(kw_src, cfg)
        save_word_freq(freq, bv_id, video_info)

    # 6. 生成情绪分析报告（JSON 格式）
    # report.py 现在不再接收 output_path，保存路径由 file_utils.save_report
    # 根据 bv_id / uname / title 自动拼接为:
    #   data/report/{uname}/{title}/{bv_id}_{时间}_report.json
    report_path = generate_report(
        comments_df=comments_df,
        danmaku_df=danmaku_df,
        label_col=label_col,
        keywords_all=keywords_all,
        keywords_pos=keywords_pos,
        keywords_neg=keywords_neg,
        bv_id=bv_id,
        video_info=video_info,
    )

    print("\n✅ 全部完成！")
    print(f"   报告: {report_path}")
    print(f"   结果目录: {args.output}/")
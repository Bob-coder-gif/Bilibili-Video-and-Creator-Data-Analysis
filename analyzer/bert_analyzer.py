"""
analyzer/bert_analyzer.py
基于 Hugging Face Transformers 的中文情绪分析

模型: uer/roberta-base-finetuned-jd-binary-chinese（二分类：负向 / 正向）

修改时间：
    2026-09-28
----------------------------------
    1. 三分类改为按"正向概率"阈值划分（config.POS_THRESHOLD / NEG_THRESHOLD）。
       原模型只有正/负两个输出，原来的映射逻辑永远不会产生"中性"，
       报告和网页里的"中性"始终为 0。现在正向概率落在中间区间的文本记为中性。
       bert_score 统一表示"正向概率"（0~1）。
    2. HF 镜像/离线设置改为 import config.hf_setup（原来在本文件写死强制离线，
       config.HF_OFFLINE 不起作用）；local_files_only 也跟随该开关。
    3. 修复推理进度条在非 verbose 模式下仍然刷屏的问题。
"""

import config.hf_setup  # noqa: F401  必须在 import transformers 之前

import logging

import pandas as pd
from tqdm import tqdm

from utils.log_utils import get_logger, log_event

logger = get_logger()

try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    import torch
except ImportError:
    raise ImportError("请先安装: pip install transformers torch")


_classifier = None   # 模块级单例，避免重复加载
_BATCH_SIZE = 64


def _has_gpu() -> bool:
    try:
        return torch.cuda.is_available()
    except Exception:
        return False


def _get_classifier(cfg):
    global _classifier
    if _classifier is None:
        model_name = cfg.BERT_MODEL_NAME
        local_only = bool(getattr(cfg, "HF_OFFLINE", True))
        logger.debug(f"[BERT] 加载模型: {model_name}（local_files_only={local_only}）")
        device = 0 if _has_gpu() else -1

        try:
            tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=local_only)
            model = AutoModelForSequenceClassification.from_pretrained(
                model_name, local_files_only=local_only
            )
        except OSError as e:
            if local_only:
                raise RuntimeError(
                    f"本地没有找到模型 {model_name} 的缓存。请把 config.HF_OFFLINE 改为 False "
                    f"跑一次任务下载模型（走国内镜像），下载完成后再改回 True。原始错误: {e}"
                ) from e
            raise

        _classifier = pipeline(
            "text-classification",
            model=model,
            tokenizer=tokenizer,
            device=device,
            truncation=True,
            max_length=512,
        )
        device_name = "GPU" if device == 0 else "CPU"
        logger.debug(f"[BERT] 模型加载完毕，使用设备: {device_name}")
        log_event("bert_model_loaded", model=model_name, device=device_name)
    return _classifier


def _positive_prob(raw_label: str, score: float) -> float:
    """把模型输出 (label, 该 label 的置信度) 统一换算成"正向概率" """
    label = raw_label.lower()
    if "pos" in label or label == "label_1":
        return score
    if "neg" in label or label == "label_0":
        return 1 - score
    return 0.5   # 无法识别的标签当作中性


def _to_label(p_pos: float, cfg) -> str:
    if p_pos >= cfg.POS_THRESHOLD:
        return "正向"
    if p_pos <= cfg.NEG_THRESHOLD:
        return "负向"
    return "中性"


def analyze(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """
    输入带 text_clean 列的 DataFrame，返回新增两列的副本：
        bert_score  正向概率（0~1）
        bert_label  正向 / 中性 / 负向
    """
    clf = _get_classifier(cfg)
    df = df.copy()
    texts = df["text_clean"].tolist()

    logger.debug(f"[BERT] 开始推理... 共 {len(texts)} 条")
    scores = []
    error_count = 0
    # 进度条只在终端日志级别为 DEBUG 时显示。
    # 注意不能用 logger.isEnabledFor(DEBUG)：logger 本身始终是 DEBUG（文件要全量），
    # 那样判断永远为 True，进度条会一直刷屏。要看的是终端 handler 的级别。
    show_progress = any(
        type(h) is logging.StreamHandler and h.level <= logging.DEBUG for h in logger.handlers
    )
    for i in tqdm(range(0, len(texts), _BATCH_SIZE), desc="BERT", disable=not show_progress):
        batch = texts[i: i + _BATCH_SIZE]
        try:
            preds = clf(batch)
            scores.extend(_positive_prob(p["label"], p["score"]) for p in preds)
        except Exception as e:
            logger.warning(f"[BERT] 批次推理出错: {e}，该批次按中性处理")
            error_count += 1
            scores.extend([0.5] * len(batch))

    df["bert_score"] = scores
    df["bert_label"] = [_to_label(s, cfg) for s in scores]
    log_event("bert_inference_done", count=len(texts), error_batches=error_count)
    return df

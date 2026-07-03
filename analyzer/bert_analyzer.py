"""
analyzer/bert_analyzer.py
基于 Hugging Face Transformers 的中文情绪分析
默认模型: uer/roberta-base-finetuned-jd-binary-chinese
  - label 0 → 负向
  - label 1 → 正向
首次运行会自动下载模型（约 400 MB）

修改时间：
    2026-06-27
----------------------------------
    国内网络适配：在 import transformers 之前，先 import config.hf_setup，
    它会设置 HuggingFace 国内镜像源（hf-mirror.com）+ 离线优先模式，
    解决国内不挂梯子时 huggingface.co 连接超时（ConnectTimeout）的问题。
    ⚠️ 这一行 import 必须在 import transformers 之前，不能调换顺序。
"""

import logging
import os
import pandas as pd
from tqdm import tqdm

from utils.log_utils import get_logger, log_event

# ⚠️ 必须在 import transformers 之前设置：HF 国内镜像源 + 离线优先。
# 直接在这里硬设环境变量（而非依赖外部模块的 import 时机），确保无论从哪个
# 入口（web / main / 后台线程）进来，只要用到 BERT，设置一定已经就绪。
# 解决国内不挂梯子时 huggingface.co 连接超时（ConnectTimeout）的问题。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

logger = get_logger()

try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    import torch
except ImportError:
    raise ImportError("请先安装: pip install transformers torch")


_classifier = None   # 模块级单例，避免重复加载


def _get_classifier(model_name: str):
    global _classifier
    if _classifier is None:
        logger.debug(f"[BERT] 加载模型: {model_name}  (首次加载较慢)")
        device = 0 if _has_gpu() else -1

        # 显式分别加载 tokenizer 和 model，都带 local_files_only=True：
        # 强制只用本地缓存、绝不联网。这是解决"新版 transformers 即使设了
        # HF_HUB_OFFLINE 仍会联网查聊天模板（list_repo_templates）、导致国内
        # ConnectTimeout"的关键。AutoTokenizer / AutoModel 的 local_files_only
        # 参数在各版本都稳定支持，比把它塞进 pipeline() 更可靠。
        # 只要模型已缓存在本地（你的已缓存），就能直接加载、彻底不碰网络。
        tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name, local_files_only=True
        )

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


def _has_gpu() -> bool:
    try:
        return torch.cuda.is_available()
    except Exception:
        return False


def _map_label(raw_label: str, score: float):
    """将模型原始标签统一为 正向/负向/中性"""
    label_lower = raw_label.lower()
    # 常见 label 格式: "LABEL_0", "LABEL_1", "negative", "positive", "星级"
    if label_lower in ("label_1", "positive", "pos") or "positive" in label_lower:
        return "正向", score
    if label_lower in ("label_0", "negative", "neg") or "negative" in label_lower:
        return "负向", 1 - score
    # 星级评分型模型（1~5 星）
    try:
        stars = int(raw_label.replace("星", "").replace("star", "").strip())
        if stars >= 4:
            return "正向", score
        if stars <= 2:
            return "负向", score
        return "中性", score
    except Exception:
        pass
    return "中性", score


def analyze(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """
    输入带 text_clean 列的 DataFrame
    返回新增 bert_score / bert_label 两列的 DataFrame
    """
    clf = _get_classifier(cfg.BERT_MODEL_NAME)
    df = df.copy()
    texts = df["text_clean"].tolist()

    logger.debug(f"[BERT] 开始推理... 共 {len(texts)} 条")
    results = []
    error_count = 0
    # 批量推理（每批 64 条）
    # 进度条只在 --verbose 下显示，避免非交互终端/日志文件里刷屏
    batch_size = 64
    show_progress = logger.isEnabledFor(logging.DEBUG)
    for i in tqdm(range(0, len(texts), batch_size), desc="BERT", disable=not show_progress):
        batch = texts[i: i + batch_size]
        try:
            preds = clf(batch)
        except Exception as e:
            # 推理批次出错是异常情况，终端要看到
            logger.warning(f"[BERT] 批次推理出错: {e}，用中性填充")
            error_count += 1
            preds = [{"label": "neutral", "score": 0.5}] * len(batch)
        results.extend(preds)

    labels, scores = [], []
    for res in results:
        lbl, sc = _map_label(res["label"], res["score"])
        labels.append(lbl)
        scores.append(sc)

    df["bert_score"] = scores
    df["bert_label"] = labels
    logger.debug("[BERT] 完成")
    log_event("bert_inference_done", count=len(texts), error_batches=error_count)
    return df
"""
analyzer/bert_analyzer.py
基于 Hugging Face Transformers 的中文情绪分析
默认模型: uer/roberta-base-finetuned-jd-binary-chinese
  - label 0 → 负向
  - label 1 → 正向
首次运行会自动下载模型（约 400 MB）
"""

import pandas as pd
from tqdm import tqdm

try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    import torch
except ImportError:
    raise ImportError("请先安装: pip install transformers torch")


_classifier = None   # 模块级单例，避免重复加载


def _get_classifier(model_name: str):
    global _classifier
    if _classifier is None:
        print(f"[BERT] 加载模型: {model_name}  (首次加载较慢)")
        device = 0 if _has_gpu() else -1
        _classifier = pipeline(
            "text-classification",
            model=model_name,
            tokenizer=model_name,
            device=device,
            truncation=True,
            max_length=512,
        )
        print(f"[BERT] 模型加载完毕，使用设备: {'GPU' if device == 0 else 'CPU'}")
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

    print("[BERT] 开始推理...")
    results = []
    # 批量推理（每批 64 条）
    batch_size = 64
    for i in tqdm(range(0, len(texts), batch_size), desc="BERT"):
        batch = texts[i: i + batch_size]
        try:
            preds = clf(batch)
        except Exception as e:
            print(f"[BERT] 批次推理出错: {e}，用中性填充")
            preds = [{"label": "neutral", "score": 0.5}] * len(batch)
        results.extend(preds)

    labels, scores = [], []
    for res in results:
        lbl, sc = _map_label(res["label"], res["score"])
        labels.append(lbl)
        scores.append(sc)

    df["bert_score"] = scores
    df["bert_label"] = labels
    print("[BERT] 完成")
    return df

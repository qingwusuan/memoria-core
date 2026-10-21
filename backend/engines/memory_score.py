"""记忆检索评分（纯函数，不依赖 ChromaDB / embedding，便于单测）。

旧实现只用向量距离排序，入库时算出的 `importance` 和入库时间 `ts`
从未参与排序，导致「三个月前的重要约定」永远输给「昨天随口一句」。
"""
from __future__ import annotations

import math
import time
from typing import Optional

from backend import config


def recency_score(ts, now: Optional[float] = None,
                  decay_per_day: Optional[float] = None) -> float:
    """时间新鲜度：指数衰减，今天≈1.0，越久越趋近 0；坏数据返回 0。"""
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        return 0.0
    decay = config.DEFAULT_DECAY_PER_DAY if decay_per_day is None else decay_per_day
    now = time.time() if now is None else now
    days = max(0.0, (now - ts) / 86400.0)
    return math.exp(-decay * days)


def similarity_from_distance(distance) -> float:
    """Chroma cosine distance → 相似度，裁剪到 [0, 1]。"""
    try:
        distance = float(distance)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, 1.0 - distance))


def hybrid_score(similarity: float, importance: float, recency: float) -> float:
    """三项加权：语义相关、重要程度、时间新鲜度。"""
    return (
        config.MEMORY_WEIGHT_SIMILARITY * similarity
        + config.MEMORY_WEIGHT_IMPORTANCE * max(0.0, min(1.0, importance))
        + config.MEMORY_WEIGHT_RECENCY * recency
    )

"""数据模型"""
from pydantic import BaseModel
from typing import Optional


class EventItem(BaseModel):
    """记忆事件条目"""
    summary: str             # 一句话概括
    importance: float        # 重要性 0-1
    tags: list[str] = []     # 标签

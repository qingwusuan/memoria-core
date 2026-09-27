"""agents 包内纯函数工具（与 main.py 底部同名函数等价，避免对 main 全局依赖）。"""
from __future__ import annotations

import re


def split_suggest(reply: str) -> tuple[str, str]:
    """拆分叙事正文与建议栏。返回 (body, suggest)。"""
    lines = reply.split("\n")
    idx = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("普通建议") or s.startswith("坏坏建议"):
            idx = i
            break
    if idx is None:
        return reply, ""
    body = "\n".join(lines[:idx]).rstrip()
    suggest = "\n".join(lines[idx:]).strip()
    return body, suggest


def hanzi_count(text: str) -> int:
    """统计中文字符数。"""
    return len(re.findall(r'[\u4e00-\u9fff]', text))

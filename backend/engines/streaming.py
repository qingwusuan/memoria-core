"""SSE 事件格式化（纯函数，便于单测）。

协议很简单：每个事件两行，`event:` 标明类型，`data:` 是 JSON。
前端按空行切分事件，所以 payload 里绝不能出现裸换行——json.dumps 已保证。
"""
from __future__ import annotations

import json
from typing import Any


def format_sse(event: str, data: Any) -> str:
    """把一个事件编码成 SSE 帧。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def parse_sse(text: str) -> list[tuple[str, Any]]:
    """解析 SSE 文本（测试与调试用）。"""
    events: list[tuple[str, Any]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data_lines = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if data_lines:
            events.append((event, json.loads("\n".join(data_lines))))
    return events

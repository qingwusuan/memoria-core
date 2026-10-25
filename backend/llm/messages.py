"""把文本 + 图片拼成 OpenAI 兼容的 message content（纯函数，便于单测）。"""
from __future__ import annotations


def build_user_content(prompt: str, images=None):
    """无图返回字符串；有图返回多模态数组。

    图片支持 data URL（`data:image/png;base64,...`）或可访问的 http(s) URL。
    """
    if not images:
        return prompt
    parts = [{"type": "text", "text": prompt}]
    for url in images:
        if not url:
            continue
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts if len(parts) > 1 else prompt

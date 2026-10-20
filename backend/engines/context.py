"""上下文预算与滚动摘要。

解决的问题：前端每次把整段会话历史回传，旧实现直接 `history[-20:]` 塞进 prompt。
角色扮演单轮 500~1500 字时，20 轮就是两三万 token，既贵又会让模型「忘了开头」。
这里把历史按 token 预算切成「保留窗口 + 被挤出的前缀」，前缀交给 LLM 压缩成一段
滚动摘要，下一轮以【早前对话摘要】注入，长局才不会一路漂移。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Callable, Optional

from backend import config

_logger = logging.getLogger("uvicorn.error")

# 中日韩统一表意文字：按字计 token；其余按 4 字符 ≈ 1 token。
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

SUMMARY_SYSTEM = (
    "你是对话压缩器。把给定的小说式角色扮演对话压缩成一段客观摘要，"
    "供后续续写时当作「早前剧情」使用。只保留对后续有影响的信息："
    "关系进展、承诺与约定、称呼变化、未解决的冲突、重要事件与场景。"
    "不要抒情，不要评论，不要编造未发生的事。用第三人称，200~400 字。"
)


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：中文按 0.75 token/字，其他按 4 字符/token。"""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = max(0, len(text) - cjk)
    return int(cjk * 0.75 + other / 4) + 4


def split_by_budget(history: list[dict],
                    budget_tokens: Optional[int] = None) -> tuple[list[dict], list[dict]]:
    """按预算从末尾往前保留，返回 (保留的近轮, 被挤出的前缀)。

    最后一条永远保留：否则当前这一轮就没有上下文锚点了。
    """
    history = list(history or [])
    budget = config.HISTORY_TOKEN_BUDGET if budget_tokens is None else budget_tokens
    used = 0
    start = len(history)
    for i in range(len(history) - 1, -1, -1):
        cost = estimate_tokens(str(history[i].get("content", "")))
        if used + cost > budget and start < len(history):
            break
        used += cost
        start = i
    return history[start:], history[:start]


def _safe_persona(persona: str) -> str:
    """角色名可能是中文：用「可读前缀 + 哈希」做目录名，避免非法路径。"""
    raw = (persona or "default").strip() or "default"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    readable = re.sub(r"[^A-Za-z0-9_-]", "", raw)[:16]
    return f"{readable}-{digest}" if readable else digest


class SummaryStore:
    """按 (角色, 会话) 持久化滚动摘要，重启后仍能接上。"""

    def __init__(self, persona: str, session_id: str = ""):
        self.persona = persona or "default"
        self.session_id = session_id or "default"
        self.dir = config.DATA_DIR / "summaries" / _safe_persona(self.persona)
        self.path = self.dir / f"{_sanitize_session(self.session_id)}.json"

    def load(self) -> dict:
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self, summary: str, covered: int) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "summary": summary,
            "covered": int(covered),
            "updated_at": time.time(),
        }
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(self.path)


def _sanitize_session(session_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", str(session_id or ""))[:40]
    return cleaned or "default"


def _render_turns(turns: list[dict], limit: int = 6000) -> str:
    lines, used = [], 0
    for turn in turns:
        role = turn.get("role", "user")
        label = {"user": "用户", "assistant": "角色", "action": "动作"}.get(role, role)
        content = str(turn.get("content", "")).strip()
        if not content:
            continue
        line = f"{label}: {content}"
        if used + len(line) > limit:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)


def summarize_turns(turns: list[dict], previous_summary: str = "",
                    llm: Optional[Callable[..., str]] = None) -> str:
    """把被挤出窗口的对话压缩成一段摘要；失败时返回上一次的摘要，不阻断主流程。"""
    text = _render_turns(turns)
    if not text.strip():
        return previous_summary

    if llm is None:
        from backend.llm.deepseek import chat as llm  # 延迟导入，便于单测替换

    prompt = ""
    if previous_summary.strip():
        prompt += f"【已有摘要】\n{previous_summary.strip()}\n\n"
    prompt += (
        "【新增的被挤出对话】\n"
        f"{text}\n\n"
        "请输出合并后的最新摘要（含已有摘要里仍然有效的信息），200~400 字。"
    )
    try:
        result = llm(prompt, system=SUMMARY_SYSTEM, temperature=0.2, max_tokens=600)
    except Exception as e:  # 摘要失败不该毁掉这一轮对话
        _logger.warning("滚动摘要失败，沿用旧摘要: %s", e)
        return previous_summary
    result = (result or "").strip()
    return result[:config.SUMMARY_MAX_CHARS] if result else previous_summary


def maybe_update_summary(persona: str, session_id: str, dropped: list[dict],
                         llm: Optional[Callable[..., str]] = None) -> str:
    """按需更新滚动摘要：被挤出的轮次累计够多才再压一次，避免每轮多打一次 LLM。"""
    if not dropped:
        return ""
    store = SummaryStore(persona, session_id)
    state = store.load()
    summary = str(state.get("summary", "") or "")
    covered = int(state.get("covered", 0) or 0)
    covered = max(0, min(covered, len(dropped)))

    if not summary or len(dropped) - covered >= config.SUMMARY_MIN_NEW_TURNS:
        summary = summarize_turns(dropped[covered:], previous_summary=summary, llm=llm)
        if summary:
            try:
                store.save(summary, covered=len(dropped))
            except OSError as e:
                _logger.warning("滚动摘要写入失败: %s", e)
    return summary

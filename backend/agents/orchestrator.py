"""Orchestrator —— 对话编排器。

按固定时序驱动本轮对话：
  1. 性格分析（降频，LLM）+ 敏感点应用（本地）→ 持久化
  2. 主回复（同步）
  3. 事件入库判定 → 返回 store_task（由 main 交给 BackgroundTasks 异步执行）

原 main.py chat() 内联的 3 次隐性 LLM 调用（性格分析 / 主回复 / 事件入库）
在此显性化为 Agent 协作。行为保持等价：性格链路同步、事件入库异步。
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from backend.engines import memory
from backend.engines import context
from backend.agents.base import Agent
from backend.agents.personality import PersonalityAnalyzerAgent
from backend.agents.responder import ResponderAgent
from backend.agents.memory_extractor import MemoryExtractorAgent
from backend.agents.util import split_suggest, hanzi_count

_logger = logging.getLogger("uvicorn.error")


class Orchestrator:
    """编排 chat 全流程。构造注入三个子 Agent，消除对 main.py 全局依赖。"""

    def __init__(
        self,
        persona: str,
        *,
        personality_agent: PersonalityAnalyzerAgent,
        responder_agent: ResponderAgent,
        memory_agent: MemoryExtractorAgent,
    ):
        self._persona = persona
        self._personality = personality_agent
        self._responder = responder_agent
        self._memory = memory_agent

    # ---- 对外主入口（同步，await 侧负责放线程池）----
    def chat_sync(
        self,
        *,
        history: list,
        message: str,
        action: str,
        character_name: str,
        character_guide: str,
        scene_hint: str,
        user_nickname: str,
        suggest_normal: bool,
        suggest_naughty: bool,
        instructions: list,
        session_id: str = "",
        narrative_person: str = "third",
    ) -> tuple[str, Optional[dict], Optional[Callable[[], None]]]:
        """同步执行本轮完整对话，返回 (reply, snapshot, store_task)。

        store_task 为可选的入库可调用对象，由 main 交给 BackgroundTasks 执行；
        行为等价于旧 chat() 的事件条件化异步入库。
        """
        # ── 1. 性格分析（LLM，降频）+ 敏感点（本地）→ 保存 ──
        if self._personality.state is not None:
            summary = self._build_summary(
                history, message, action, character_name
            )
            if self._personality.register_round():
                self._personality.analyze(summary)
            self._personality.apply_sensitive_points(message or action)
            self._personality.save()

        # ── 2. 上下文预算：近期对话按 token 预算截取，挤出的前缀滚动摘要 ──
        recent_dialogue, dropped = context.split_by_budget(history)
        early_summary = ""
        if dropped:
            try:
                early_summary = context.maybe_update_summary(
                    self._persona, session_id, dropped
                )
            except Exception as e:  # 摘要链路失败不能挡住回复
                _logger.warning("滚动摘要不可用，本轮跳过: %s", e)

        # ── 3. 主回复（同步）──
        reply = self._responder.run(
            character_guide=character_guide,
            recent_dialogue=recent_dialogue,
            current_message=message,
            personality=self._personality.state,
            character_name=character_name,
            suggest_normal=suggest_normal,
            suggest_naughty=suggest_naughty,
            scene_hint=scene_hint,
            instructions=instructions,
            user_nickname=user_nickname,
            action=action,
            early_summary=early_summary,
            narrative_person=narrative_person,
        )

        # ── 4. 事件入库判定（条件化，异步）──
        store_task = self._build_store_task(
            reply, message, action, character_name
        )

        return reply, self._personality.snapshot(), store_task

    def stream_sync(self, *, history: list, message: str, action: str,
                    character_name: str, character_guide: str, scene_hint: str,
                    user_nickname: str, suggest_normal: bool, suggest_naughty: bool,
                    instructions: list, session_id: str = "",
                    narrative_person: str = "third"):
        """流式版 chat_sync：先做性格/预算/摘要，再逐段 yield 正文。

        事件入库仍是异步的：流结束后在后台线程里跑，不拖住响应。
        """
        # ── 1. 性格分析（与 chat_sync 完全一致）──
        if self._personality.state is not None:
            summary = self._build_summary(history, message, action, character_name)
            if self._personality.register_round():
                self._personality.analyze(summary)
            self._personality.apply_sensitive_points(message or action)
            self._personality.save()

        # ── 2. 上下文预算 + 滚动摘要 ──
        recent_dialogue, dropped = context.split_by_budget(history)
        early_summary = ""
        if dropped:
            try:
                early_summary = context.maybe_update_summary(
                    self._persona, session_id, dropped
                )
            except Exception as e:
                _logger.warning("滚动摘要不可用，本轮跳过: %s", e)

        # ── 3. 流式主回复 ──
        chunks: list[str] = []
        for delta in self._responder.stream(
            character_guide=character_guide,
            recent_dialogue=recent_dialogue,
            current_message=message,
            personality=self._personality.state,
            character_name=character_name,
            suggest_normal=suggest_normal,
            suggest_naughty=suggest_naughty,
            scene_hint=scene_hint,
            instructions=instructions,
            user_nickname=user_nickname,
            action=action,
            early_summary=early_summary,
            narrative_person=narrative_person,
        ):
            chunks.append(delta)
            yield delta

        # ── 4. 事件入库（后台线程，不阻塞收尾）──
        reply = "".join(chunks)
        store_task = self._build_store_task(reply, message, action, character_name)
        if store_task is not None:
            threading.Thread(target=store_task, daemon=True).start()

    # ---- 内部 ----
    @staticmethod
    def _build_summary(
        history: list, message: str, action: str, character_name: str
    ) -> str:
        """构建性格分析用的对话摘要（最近 3 轮），与原 chat() 等价。"""
        summary_lines = []
        for turn in history[-6:]:
            content = turn.get("content", "")[:200]
            role = "你" if turn.get("role") == "user" else character_name
            if turn.get("role") == "action":
                role = f"{character_name}观察到"
            summary_lines.append(f"{role}: {content}")
        if action and action.strip():
            summary_lines.append(f"{character_name}得知你要做: {action[:200]}")
        return "\n".join(summary_lines) if summary_lines else (message or action)

    def _build_store_task(
        self, reply: str, message: str, action: str, character_name: str
    ) -> Optional[Callable[[], None]]:
        """构造事件入库任务；寒暄轮（双方无实质内容）返回 None 跳过。"""
        if not (message.strip() or action.strip()):
            return None
        body_text = split_suggest(reply)[0]
        user_part = message.strip() if message.strip() else f"（动作）{action.strip()}"
        if not ((action and action.strip()) or len(user_part) >= 8 or hanzi_count(body_text) >= 40):
            return None
        turn_text = f"用户：{user_part}\n{character_name}：{body_text}"
        # 闭包内固定 persona，避免后续 persona 切换影响此任务
        persona = self._persona

        def _task():
            memory.store_chat_events_from_dialogue(
                turn_text, persona=persona
            )
        return _task

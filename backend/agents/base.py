"""Agent 基类：统一 LLM 调用入口。

职责：
1. 收敛 LLM 通道：所有子 Agent 通过 `self.llm()` 调用模型，统一注入实现，
   便于测试注入假通道 / 后续替换 provider，无需感知 backend.llm 细节。
2. 声明 Agent 独立性约定：每个子 Agent 只持有自己的 persona 与该 Agent
   职责所需数据，禁止 import backend.main 的全局变量（依赖通过构造注入）。
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

_logger = logging.getLogger("uvicorn.error")


def default_llm_chat(prompt: str, system: str = "", temperature: float = 0.3,
                     max_tokens: int = 2000) -> str:
    """默认 LLM 通道（与旧 main.chat_llm 一致）。"""
    from backend.llm.deepseek import chat
    return chat(prompt, system=system, temperature=temperature, max_tokens=max_tokens)


class Agent:
    """所有 Memoria 子 Agent 的基类。

    :param name: Agent 名（responder / personality_analyzer / memory_extractor）
    :param persona: 当前角色名
    :param llm_impl: LLM 可调用对象，签名 (prompt, system=, temperature=, max_tokens=) -> str
    """

    name: str = "agent"
    temperature: float = 0.3
    max_tokens: int = 2000

    def __init__(self, name: str, persona: str,
                 llm_impl: Optional[Callable[..., str]] = None):
        self.name = name
        self.persona = persona
        self._llm_impl = llm_impl or default_llm_chat

    def llm(self, prompt: str, *, system: str = "",
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None) -> str:
        """统一 LLM 入口。子 Agent 只允许走此通道调用模型。"""
        return self._llm_impl(
            prompt,
            system=system,
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=self.max_tokens if max_tokens is None else max_tokens,
        )

    def run(self, **ctx):  # pragma: no cover - 子类实现
        raise NotImplementedError

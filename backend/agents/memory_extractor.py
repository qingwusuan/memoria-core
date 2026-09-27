"""MemoryExtractorAgent —— 聊天事件提取入库 Agent。

收管对话文本 → 事件入库（含语义去重），以及「导入记录末尾场景」的锚定读写。
与原 main.py 直接调用 memory.store_chat_events_from_dialogue / save_last_scene
行为等价；调用时机（同步/后台）由 Orchestrator 决定。
"""
from __future__ import annotations

from backend.engines import memory
from backend.agents.base import Agent


class MemoryExtractorAgent(Agent):

    name = "memory_extractor"
    # 事件提取本身是逐场景 LLM 调用 + 限速 sleep，重 IO；本 Agent 不直接持 LLM
    # 通道，由 orchestrator 决定是否放线程池。保留基类接口但此处仅封装 memory API。

    def __init__(self, persona: str, llm_impl=None):
        super().__init__(self.name, persona, llm_impl=llm_impl)

    def store_dialogue(self, dialogue: str, *, dedup_threshold: float = 0.30) -> list:
        """提取事件并入库，返回新写入的事件 id 列表。"""
        return memory.store_chat_events_from_dialogue(
            dialogue, persona=self.persona, dedup_threshold=dedup_threshold
        )

    def extract_events(self, dialogue: str) -> list:
        """仅提取事件（不落库），供性格分析摘要等使用。"""
        return memory.extract_events(dialogue)

    def save_last_scene(self, dialogue: str):
        """记录导入文本末尾场景，供后续接续对话锚定。"""
        memory.save_last_scene(self.persona, dialogue)

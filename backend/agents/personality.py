"""PersonalityAnalyzerAgent —— 性格分析子 Agent。

收管单一角色（persona）的完整性格生命周期：
- 磁盘读写（load / save）：state.json 中的性格状态与敏感点表
- 分析（analyze）：对每轮对话做性格 delta 漂移分析（一次 LLM 调用）
- 敏感点（apply_sensitive_points）：本地匹配瞬时拉升（无 LLM）

与原 main.py 全局 _load_personality/_save_personality 行为等价；
消除对 main.py 全局变量（_current_personality/_sensitive_points）的 import 依赖，
由 Orchestrator 构造注入本 Agent 实例使用。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from backend import config
from backend.engines import personality as engine
from backend.engines.personality import PersonalityState, SensitivePoint
from backend.agents.base import Agent

_logger = logging.getLogger("uvicorn.error")

# 性格状态目录（按角色存储）——与 main 原 PERSONALITIES_DIR 保持一致
PERSONALITIES_DIR = config.DATA_DIR / "personalities"


class PersonalityAnalyzerAgent(Agent):

    name = "personality_analyzer"
    # analyze_delta 默认温度/长度，与旧 chat_llm 默认一致
    temperature = 0.3
    max_tokens = 2000
    # 每 N 轮做一次 LLM 分析（与旧 _analyze_counters % 5 == 1 等价）
    ANALYZE_INTERVAL = 5

    def __init__(self, persona: str, llm_impl=None):
        super().__init__(self.name, persona, llm_impl=llm_impl)
        self._state: Optional[PersonalityState] = None
        self._sensitive_points: list[SensitivePoint] = []
        self._round_counter = 0

    # ---- 状态访问 ----
    @property
    def state(self) -> Optional[PersonalityState]:
        return self._state

    @property
    def sensitive_points(self) -> list[SensitivePoint]:
        return self._sensitive_points

    # ---- 持久化 ----
    @staticmethod
    def _state_file(persona: str) -> Path:
        return PERSONALITIES_DIR / persona / "state.json"

    def load(self):
        """从磁盘加载该 persona 的性格状态与敏感点表（含旧版迁移逻辑）。"""
        file = self._state_file(self.persona)

        # 兼容旧版：若旧 personality.json 仍存在且新位置无文件，迁移到该角色名下
        old_file = config.DATA_DIR / "personality.json"
        if old_file.exists() and not file.exists():
            file.parent.mkdir(parents=True, exist_ok=True)
            try:
                old_file.rename(file)
            except OSError as e:
                _logger.warning("旧 personality.json 迁移失败: %s", e)

        if file.exists():
            data = json.loads(file.read_text("utf-8"))
            self._state = PersonalityState.from_dict(data.get("state", {}))
            self._sensitive_points = [
                SensitivePoint(**sp) for sp in data.get("sensitive_points", [])
            ]
        else:
            self._state = PersonalityState()
            self._sensitive_points = []
        return self

    def save(self):
        """持久化当前性格状态与敏感点表到磁盘。"""
        file = self._state_file(self.persona)
        file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "state": self._state.to_dict(),
            "persona": self.persona,
            "sensitive_points": [
                {
                    "trigger_keywords": sp.trigger_keywords,
                    "target_dimension": sp.target_dimension,
                    "delta": sp.delta,
                    "cooldown_rounds": sp.cooldown_rounds,
                    "description": sp.description,
                }
                for sp in self._sensitive_points
            ],
        }
        file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
        )

    # ---- 降频控制 ----
    def register_round(self) -> bool:
        """登记一轮对话，返回本轮是否应当执行 LLM 分析（每 5 轮一次）。"""
        self._round_counter += 1
        return self._round_counter % self.ANALYZE_INTERVAL == 1

    # ---- 重置 ----
    def reset(self):
        """重置为全新性格状态，并立即持久化。"""
        self._state = PersonalityState()
        self._sensitive_points = []
        self._round_counter = 0
        self.save()
        return self

    def add_sensitive_point(self, point: SensitivePoint):
        """追加一条敏感点并立即持久化。"""
        self._sensitive_points.append(point)
        self.save()
        return self

    def set_sensitive_points(self, points: list[SensitivePoint]):
        """整体替换敏感点表并立即持久化。"""
        self._sensitive_points = list(points)
        self.save()
        return self

    # ---- 分析 / 敏感点 ----
    def analyze(self, dialogue_summary: str, *, llm_chat=None) -> Optional[PersonalityState]:
        """LLM 分析性格漂移并应用 delta。失败时降级保留旧状态（不阻断对话）。

        llm_chat 可覆盖本次调用的 LLM 通道：主对话链路默认用 self.llm（主锁）；
        后台导入等场景可由调用方注入 chat_llm_background（后台锁），
        避免后台分析占用主对话锁阻塞聊天。
        """
        if self._state is None:
            return None
        llm_chat = llm_chat or self.llm
        try:
            self._state = engine.analyze_delta(
                self._state, dialogue_summary, llm_chat=llm_chat
            )
        except Exception as exc:  # noqa: BLE001 - 保持旧行为：分析失败不阻断
            _logger.warning("analyze_delta 降级（保留旧结果）: %s", exc)
            self._state = self._state
        return self._state

    def apply_sensitive_points(self, dialogue_text: str) -> Optional[PersonalityState]:
        """本地敏感点匹配（无 LLM），每轮都执行。"""
        if self._state is None:
            return None
        self._state = engine.apply_sensitive_points(
            self._state, dialogue_text, self._sensitive_points
        )
        return self._state

    # ---- 快照 ----
    def snapshot(self) -> Optional[dict]:
        """生成前端可用的性格快照；state 未初始化时返回 None。"""
        p = self._state
        if p is None:
            return None
        return {
            "round_count": p.round_count,
            "intimacy": p.intimacy,
            "top_gaps": [
                {
                    "dimension": engine.DIMENSION_NAMES[i],
                    "surface": p.surface(i),
                    "deep": p.deep(i),
                    "gap": p.gap(i),
                }
                for i in p.top_gap_dimensions(3)
            ],
        }

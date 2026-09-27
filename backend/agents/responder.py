"""ResponderAgent —— 主回复 Agent（同步、唯一用户可见路径）。

收管：
- 构建聊天 prompt（character guide + 最近对话 + 当前消息 + 性格 + 指令）
- 主 LLM 回复 + 空回复高温度重试兜底
- 「字数加强」指令下的短回复续写补完

与原 main.py chat() 内联主回复逻辑行为等价。
"""
from __future__ import annotations

import logging
from typing import Optional

from backend.engines import prompt_builder
from backend.engines.personality import PersonalityState
from backend.agents.base import Agent
from backend.agents.util import split_suggest, hanzi_count

_logger = logging.getLogger("uvicorn.error")

# 主回复正文兜底阈值：正文不足 200 汉字视为异常中断
CONTINUE_THRESHOLD = 200
CONTINUE_ANCHOR = 200


class ResponderAgent(Agent):

    name = "responder"
    # 主回复参数：与旧 chat_llm 调用一致（高温、长额度防截断）
    temperature = 0.8
    max_tokens = 5000

    def __init__(self, persona: str, llm_impl=None):
        super().__init__(self.name, persona, llm_impl=llm_impl)

    def build_prompts(
        self,
        *,
        character_guide: str,
        recent_dialogue: list,
        current_message: str,
        personality: Optional[PersonalityState],
        character_name: str,
        suggest_normal: bool,
        suggest_naughty: bool,
        scene_hint: str,
        instructions: list,
        user_nickname: str,
        action: str,
    ) -> tuple[str, str]:
        """构建 (system_prompt, user_prompt)。"""
        return prompt_builder.build_chat_messages(
            character_guide=character_guide,
            recent_dialogue=recent_dialogue,
            current_message=current_message,
            personality=personality,
            character_name=character_name,
            persona=self.persona,
            suggest_normal=suggest_normal,
            suggest_naughty=suggest_naughty,
            scene_hint=scene_hint,
            instructions=instructions,
            user_nickname=user_nickname,
            action=action,
        )

    def run(self, **ctx) -> str:
        """生成主回复。

        ctx 兼容 prompt_builder.build_chat_messages / 主回复所需全部字段：
        character_guide / recent_dialogue / current_message / personality /
        character_name / suggest_normal / suggest_naughty / scene_hint /
        instructions / user_nickname / action
        """
        system_prompt, user_prompt = self.build_prompts(**ctx)

        reply = self.llm(user_prompt, system=system_prompt)

        # 空回复兜底：换更高温度再试一次；仍为空则如实报错（严禁编造文案）
        if not reply or not reply.strip():
            try:
                reply = self.llm(user_prompt, system=system_prompt, temperature=1.0)
            except Exception as e:
                _logger.warning("空回复高温度重试失败: %s", e)
                reply = None
            if not reply or not reply.strip():
                raise RuntimeError("LLM 返回空回复，已重试仍无内容")

        # 字数加强续写兜底：仅当指令要求且正文过短时，以末尾为锚点续写一次
        instructions = ctx.get("instructions") or []
        if any("字数加强" in inst for inst in instructions):
            body, suggest = split_suggest(reply)
            if hanzi_count(body) < CONTINUE_THRESHOLD:
                tail = body[-CONTINUE_ANCHOR:]
                continue_prompt = (
                    f"【续写任务】以下是上一条回复的叙事正文末尾（不要重复这段内容）：\n"
                    f"……{tail}\n\n"
                    f"请紧接上文把这段剧情自然、饱满地继续写下去，展开动作、神态、心理、环境与对话，"
                    f"按剧情需要推进，不要凑字数、不要重复已有内容。"
                    f"直接输出续写内容，不要任何解释、不要输出建议栏。"
                )
                extra = self.llm(
                    continue_prompt,
                    system="你是续写助手，负责把异常中断的叙事正文自然补完。"
                           "只输出补充内容，保持第三人称与原有风格，不要输出建议栏。",
                )
                extra_body, _ = split_suggest(extra)
                reply = body + "\n\n" + extra_body + ("\n\n" + suggest if suggest else "")

        return reply

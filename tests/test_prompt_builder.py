"""prompt 组装回归测试。

重点守住两个曾经出过的问题：
  1. 角色设定在 system 和 user 两处各拼一遍（白烧 token）；
  2. 早前对话摘要没有注入位。
"""
import sys
import types
import unittest
from unittest.mock import patch

from backend.engines import prompt_builder

GUIDE = "你是小夏，18岁女高中生，说话带刺。"
RECENT = [
    {"role": "user", "content": "你昨天为什么生气？"},
    {"role": "assistant", "content": "我哪有生气。"},
]


def _fake_memory():
    fake = types.ModuleType("backend.engines.memory")
    fake.search_memories = lambda *args, **kwargs: []
    return fake


class PromptBuilderTest(unittest.TestCase):
    def setUp(self):
        # 避开 chromadb / sentence-transformers：让检索返回空
        self._patcher = patch.dict(sys.modules, {"backend.engines.memory": _fake_memory()})
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_guide_injected_once_in_chat_messages(self):
        system, user = prompt_builder.build_chat_messages(
            GUIDE, RECENT, "我保证这次不鸽你。", character_name="小夏"
        )
        self.assertIn(GUIDE, system)
        self.assertNotIn(GUIDE, user)
        self.assertNotIn("【小夏设定】", user)

    def test_build_prompt_keeps_guide_by_default(self):
        prompt = prompt_builder.build_prompt(GUIDE, RECENT, "你好", character_name="小夏")
        self.assertIn("【小夏设定】", prompt)
        self.assertIn(GUIDE, prompt)

    def test_early_summary_is_injected_before_recent_dialogue(self):
        _, user = prompt_builder.build_chat_messages(
            GUIDE, RECENT, "继续。", character_name="小夏",
            early_summary="两人上周约好去看海，但一直没去成。",
        )
        self.assertIn("【早前对话摘要】", user)
        self.assertLess(user.index("【早前对话摘要】"), user.index("【近期对话】"))

    def test_user_nickname_and_action_are_rendered(self):
        prompt = prompt_builder.build_prompt(
            GUIDE,
            [{"role": "action", "content": "推门进去"}],
            "",
            character_name="小夏",
            user_nickname="阿岚",
        )
        self.assertIn("（阿岚的动作）推门进去", prompt)
        self.assertIn("【现在】阿岚:", prompt)


if __name__ == "__main__":
    unittest.main()

"""回复模式测试：聊天模式必须是短句口语，且压过小说体与字数加强。"""
import sys
import types
import unittest
from unittest.mock import patch

from backend.engines import prompt_builder

GUIDE = "你是小夏，18岁女高中生。"


def _fake_memory():
    fake = types.ModuleType("backend.engines.memory")
    fake.search_memories = lambda *a, **k: []
    return fake


class ReplyModeTest(unittest.TestCase):
    def setUp(self):
        self._patcher = patch.dict(sys.modules, {"backend.engines.memory": _fake_memory()})
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_chat_mode_injects_short_reply_rules(self):
        system, _ = prompt_builder.build_chat_messages(
            GUIDE, [], "在吗", character_name="小夏", reply_mode="chat"
        )
        self.assertIn("日常聊天", system)
        self.assertIn("1~3 句", system)
        self.assertIn("不写动作旁白", system)

    def test_novel_mode_has_no_chat_block(self):
        system, _ = prompt_builder.build_chat_messages(
            GUIDE, [], "在吗", character_name="小夏", reply_mode="novel"
        )
        self.assertNotIn("日常聊天", system)

    def test_chat_mode_ignores_length_instruction(self):
        system, _ = prompt_builder.build_chat_messages(
            GUIDE, [], "在吗", character_name="小夏", reply_mode="chat",
            instructions=["【字数加强】请写长一点"],
        )
        self.assertIn("日常聊天", system)
        self.assertNotIn("500~1500字", system)

    def test_novel_mode_keeps_length_instruction(self):
        system, _ = prompt_builder.build_chat_messages(
            GUIDE, [], "在吗", character_name="小夏", reply_mode="novel",
            instructions=["【字数加强】请写长一点"],
        )
        self.assertIn("500~1500字", system)


if __name__ == "__main__":
    unittest.main()

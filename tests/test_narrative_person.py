"""叙事视角测试：第一人称与第三人称的 system prompt 必须真的不同。"""
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


class NarrativePersonTest(unittest.TestCase):
    def setUp(self):
        self._patcher = patch.dict(sys.modules, {"backend.engines.memory": _fake_memory()})
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_first_person_prompt(self):
        system, _ = prompt_builder.build_chat_messages(
            GUIDE, [], "在吗", character_name="小夏", narrative_person="first"
        )
        self.assertIn("第一人称", system)
        self.assertIn("用「我」指代小夏", system)
        self.assertNotIn("以第三人称叙事视角回复", system)

    def test_third_person_prompt_is_default(self):
        system, _ = prompt_builder.build_chat_messages(GUIDE, [], "在吗", character_name="小夏")
        self.assertIn("以第三人称叙事视角回复", system)
        self.assertNotIn("第一人称", system)

    def test_first_person_allows_you(self):
        system, _ = prompt_builder.build_chat_messages(
            GUIDE, [], "在吗", character_name="小夏", user_nickname="阿岚", narrative_person="first"
        )
        self.assertIn("可以直接用「你」", system)

    def test_third_person_requires_nickname(self):
        system, _ = prompt_builder.build_chat_messages(
            GUIDE, [], "在吗", character_name="小夏", user_nickname="阿岚", narrative_person="third"
        )
        self.assertIn("必须使用「阿岚」", system)


if __name__ == "__main__":
    unittest.main()

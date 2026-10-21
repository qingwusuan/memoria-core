"""滚动摘要的落盘与清理测试：删角色不能把剧情梗概留在磁盘上。"""
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from backend import config
from backend.engines import context


class SummaryLifecycleTest(unittest.TestCase):
    def setUp(self):
        self._tmp = Path("data/_test_tmp") / uuid.uuid4().hex
        self._tmp.mkdir(parents=True, exist_ok=True)

    def test_delete_persona_summaries_removes_directory(self):
        with patch.object(config, "DATA_DIR", self._tmp):
            store = context.SummaryStore("汐", "s1")
            store.save("雨里第一次见面", covered=4)
            self.assertEqual(context.list_persona_summaries("汐"), ["s1"])

            removed = context.delete_persona_summaries("汐")

            self.assertTrue(removed)
            self.assertEqual(context.list_persona_summaries("汐"), [])
            self.assertFalse(context.summary_dir("汐").exists())

    def test_delete_persona_summaries_is_idempotent(self):
        with patch.object(config, "DATA_DIR", self._tmp):
            self.assertFalse(context.delete_persona_summaries("不存在的角色"))

    def test_personas_have_separate_summary_dirs(self):
        with patch.object(config, "DATA_DIR", self._tmp):
            context.SummaryStore("甲", "s").save("甲的故事", covered=1)
            context.SummaryStore("乙", "s").save("乙的故事", covered=1)
            context.delete_persona_summaries("甲")
            self.assertEqual(context.list_persona_summaries("甲"), [])
            self.assertEqual(context.list_persona_summaries("乙"), ["s"])


if __name__ == "__main__":
    unittest.main()

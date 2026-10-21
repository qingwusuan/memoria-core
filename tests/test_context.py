"""上下文预算与滚动摘要的单元测试（不触网、不调 LLM）。"""
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from backend import config
from backend.engines import context


class ContextTest(unittest.TestCase):
    def setUp(self):
        # 用仓库内的 data/（已 gitignore）当临时目录：沙箱下删系统临时目录会掉权限。
        self._tmp = Path("data/_test_tmp") / uuid.uuid4().hex
        self._tmp.mkdir(parents=True, exist_ok=True)

    def test_estimate_tokens_counts_chinese_higher_than_ascii(self):
        zh = context.estimate_tokens("这是一段中文")
        en = context.estimate_tokens("this is english")
        self.assertGreater(zh, en)

    def test_split_keeps_last_turn_even_when_it_exceeds_budget(self):
        history = [
            {"role": "user", "content": "早" * 5000},
            {"role": "assistant", "content": "晚" * 5000},
        ]
        kept, dropped = context.split_by_budget(history, budget_tokens=10)
        self.assertEqual(len(kept), 1)
        self.assertTrue(kept[0]["content"].startswith("晚"))
        self.assertEqual(len(dropped), 1)

    def test_split_respects_budget_and_preserves_order(self):
        history = [{"role": "user", "content": "字" * 100} for _ in range(10)]
        kept, dropped = context.split_by_budget(history, budget_tokens=200)
        self.assertEqual(len(kept) + len(dropped), 10)
        self.assertEqual(kept, history[len(dropped):])

    def test_summary_store_roundtrip(self):
        with patch.object(config, "DATA_DIR", self._tmp):
            store = context.SummaryStore("测试角色", "sess-1")
            store.save("两人约好周末去看海。", covered=6)
            loaded = store.load()
            self.assertEqual(loaded["summary"], "两人约好周末去看海。")
            self.assertEqual(loaded["covered"], 6)

    def test_summarize_turns_falls_back_to_previous_on_failure(self):
        def boom(*args, **kwargs):
            raise RuntimeError("llm down")

        result = context.summarize_turns(
            [{"role": "user", "content": "你好"}], previous_summary="旧摘要", llm=boom
        )
        self.assertEqual(result, "旧摘要")

    def test_maybe_update_summary_skips_when_not_enough_new_turns(self):
        calls = []
        with patch.object(config, "DATA_DIR", self._tmp), \
                patch.object(config, "SUMMARY_MIN_NEW_TURNS", 4):
            store = context.SummaryStore("角色", "s")
            store.save("已有摘要", covered=3)
            result = context.maybe_update_summary(
                "角色", "s",
                dropped=[{"role": "user", "content": f"第{i}轮"} for i in range(5)],
                llm=lambda *a, **k: calls.append(1) or "新摘要",
            )
            # 5 条被挤出、已覆盖 3 条，只新增 2 条 < 4，不触发重压
            self.assertEqual(result, "已有摘要")
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()

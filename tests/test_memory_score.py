"""记忆检索评分测试：确保 importance 与时间真正参与排序。"""
import time
import unittest

from backend.engines import memory_score


class MemoryScoreTest(unittest.TestCase):
    def test_recency_decays_with_age(self):
        now = time.time()
        fresh = memory_score.recency_score(now, now=now)
        month_old = memory_score.recency_score(now - 30 * 86400, now=now)
        self.assertAlmostEqual(fresh, 1.0, places=6)
        self.assertGreater(month_old, 0.0)
        self.assertLess(month_old, fresh)

    def test_recency_returns_zero_for_bad_ts(self):
        self.assertEqual(memory_score.recency_score(None), 0.0)
        self.assertEqual(memory_score.recency_score("not-a-date"), 0.0)

    def test_similarity_is_clipped(self):
        self.assertEqual(memory_score.similarity_from_distance(0.0), 1.0)
        self.assertEqual(memory_score.similarity_from_distance(2.0), 0.0)
        self.assertEqual(memory_score.similarity_from_distance(-1.0), 1.0)

    def test_important_old_memory_can_beat_trivial_new_one(self):
        now = time.time()
        old_important = memory_score.hybrid_score(
            similarity=0.65,
            importance=0.95,
            recency=memory_score.recency_score(now - 90 * 86400, now=now),
        )
        new_trivial = memory_score.hybrid_score(
            similarity=0.72,
            importance=0.10,
            recency=memory_score.recency_score(now, now=now),
        )
        self.assertGreater(old_important, new_trivial)


if __name__ == "__main__":
    unittest.main()

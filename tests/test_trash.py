"""回收站测试：列表 / 整体恢复 / 拒绝覆盖 / 彻底删除 / 路径穿越。"""
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from backend import config
from backend.engines import trash


def _make_backup(root: Path, folder: str, persona: str = "汐") -> Path:
    dest = root / "trash" / folder
    (dest / "personality").mkdir(parents=True)
    (dest / "chat_logs").mkdir(parents=True)
    (dest / "summaries").mkdir(parents=True)
    (dest / "persona.json").write_text(
        json.dumps({"name": persona, "guide": "你是汐。"}, ensure_ascii=False), "utf-8"
    )
    (dest / "personality" / "state.json").write_text('{"round_count": 3}', "utf-8")
    (dest / "chat_logs" / "s1.json").write_text('{"messages": []}', "utf-8")
    (dest / "summaries" / "s1.json").write_text('{"summary": "雨里初见"}', "utf-8")
    (dest / "last_scene_abc.json").write_text(
        json.dumps({"persona": persona, "scene": "电影院"}, ensure_ascii=False), "utf-8"
    )
    (dest / "meta.json").write_text(
        json.dumps({"persona": persona, "created_at": 1700000000.0}, ensure_ascii=False), "utf-8"
    )
    return dest


class TrashTest(unittest.TestCase):
    def setUp(self):
        self._tmp = Path("data/_test_tmp") / uuid.uuid4().hex
        self._tmp.mkdir(parents=True, exist_ok=True)
        self._personas = self._tmp / "personas"
        self._personas.mkdir(parents=True, exist_ok=True)
        self._patches = [
            patch.object(config, "DATA_DIR", self._tmp),
            patch.object(config, "PERSONAS_DIR", self._personas),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_list_backups_reads_meta_and_parts(self):
        _make_backup(self._tmp, "汐_20260101_120000")
        items = trash.list_backups()
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["persona"], "汐")
        self.assertIn("persona.json", item["parts"])
        self.assertIn("summaries", item["parts"])
        self.assertIn("last_scene", item["parts"])
        self.assertGreater(item["size_bytes"], 0)

    def test_restore_brings_back_all_parts(self):
        _make_backup(self._tmp, "汐_20260101_120000")
        result = trash.restore_backup("汐_20260101_120000")

        self.assertEqual(result["persona"], "汐")
        self.assertTrue((self._personas / "汐.json").exists())
        self.assertTrue((self._tmp / "personalities" / "汐" / "state.json").exists())
        self.assertTrue((self._tmp / "chat_logs" / "汐" / "s1.json").exists())
        self.assertTrue((self._tmp / "summaries").exists())
        self.assertEqual(len(list((self._tmp / "last_scenes").glob("*.json"))), 1)
        self.assertIn("persona", result["restored"])
        self.assertIn("summaries", result["restored"])

    def test_restore_refuses_existing_persona_unless_overwrite(self):
        _make_backup(self._tmp, "汐_20260101_120000")
        (self._personas / "汐.json").write_text("{}", "utf-8")

        with self.assertRaises(trash.TrashError):
            trash.restore_backup("汐_20260101_120000")

        result = trash.restore_backup("汐_20260101_120000", overwrite=True)
        self.assertEqual(result["persona"], "汐")

    def test_restore_rejects_path_traversal(self):
        for bad in ["../evil", "..\\evil", "a/b", ""]:
            with self.assertRaises(trash.TrashError):
                trash.restore_backup(bad)

    def test_purge_removes_directory(self):
        dest = _make_backup(self._tmp, "汐_20260101_120000")
        self.assertTrue(trash.purge_backup("汐_20260101_120000"))
        self.assertFalse(dest.exists())
        with self.assertRaises(trash.TrashError):
            trash.purge_backup("汐_20260101_120000")


if __name__ == "__main__":
    unittest.main()

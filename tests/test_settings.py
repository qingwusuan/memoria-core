"""运行时设置测试：供应商与叙事视角的校验、持久化与兜底。"""
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from backend import config
from backend.engines import settings


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = Path("data/_test_tmp") / uuid.uuid4().hex
        self._tmp.mkdir(parents=True, exist_ok=True)
        self._patches = [
            patch.object(config, "DATA_DIR", self._tmp),
            patch.object(config, "LLM_API_KEY", "sk-test-deepseek"),
            patch.object(config, "KIMI_API_KEY", "sk-test-kimi"),
            patch.object(config, "LLM_PROVIDER", "deepseek"),
            patch.object(config, "LLM_MODEL", "deepseek-v4-flash"),
            patch.object(config, "KIMI_MODEL", "kimi-k2.6"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_defaults_when_no_file(self):
        data = settings.load()
        self.assertIsNone(data["provider"])
        self.assertEqual(data["narrative_person"], "third")
        self.assertEqual(settings.effective_provider(), "deepseek")

    def test_switch_provider_persists(self):
        settings.save({"provider": "kimi"})
        self.assertEqual(settings.load()["provider"], "kimi")
        self.assertEqual(settings.effective_provider(), "kimi")
        self.assertEqual(settings.model_of("kimi"), "kimi-k2.6")

    def test_reject_unknown_provider(self):
        with self.assertRaises(ValueError):
            settings.save({"provider": "openai"})

    def test_reject_provider_without_key(self):
        with patch.object(config, "KIMI_API_KEY", ""):
            with self.assertRaises(ValueError):
                settings.save({"provider": "kimi"})

    def test_narrative_person_roundtrip(self):
        settings.save({"narrative_person": "first"})
        self.assertEqual(settings.load()["narrative_person"], "first")
        with self.assertRaises(ValueError):
            settings.save({"narrative_person": "second"})

    def test_public_view_lists_providers_and_current_model(self):
        view = settings.public_view()
        ids = [p["id"] for p in view["providers"]]
        self.assertEqual(ids, ["deepseek", "kimi"])
        self.assertEqual(view["provider"], "deepseek")
        self.assertEqual(view["model"], "deepseek-v4-flash")
        self.assertTrue(all(p["has_key"] for p in view["providers"]))


if __name__ == "__main__":
    unittest.main()

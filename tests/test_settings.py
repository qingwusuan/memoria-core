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

    def test_imported_key_overrides_env_and_is_masked(self):
        settings.set_key("kimi", "sk-kimi-1234567890abcd")
        self.assertTrue(settings.has_key("kimi"))
        self.assertEqual(settings.get_key("kimi"), "sk-kimi-1234567890abcd")
        masked = settings.mask_key(settings.get_key("kimi"))
        self.assertNotIn("1234567890", masked)
        self.assertTrue(masked.startswith("sk-"))
        self.assertTrue(masked.endswith("abcd"))

    def test_imported_key_works_without_env_key(self):
        with patch.object(config, "KIMI_API_KEY", ""):
            self.assertFalse(settings.has_key("kimi"))
            settings.set_key("kimi", "sk-imported-key-0001")
            self.assertTrue(settings.has_key("kimi"))
            settings.save({"provider": "kimi"})
            self.assertEqual(settings.effective_provider(), "kimi")

    def test_clear_key_falls_back_to_env(self):
        settings.set_key("kimi", "sk-imported-key-0001")
        settings.set_key("kimi", "")
        with patch.object(config, "KIMI_API_KEY", "sk-env-kimi"):
            self.assertEqual(settings.get_key("kimi"), "sk-env-kimi")
        with patch.object(config, "KIMI_API_KEY", ""):
            self.assertFalse(settings.has_key("kimi"))

    def test_reject_unknown_provider_key(self):
        with self.assertRaises(ValueError):
            settings.set_key("openai", "sk-x")

    def test_add_custom_provider_and_use_it(self):
        cfg = settings.add_provider("我的中转", "https://api.example.com/v1", "gpt-4o-mini")
        self.assertEqual(cfg["id"], "custom")
        self.assertIn("custom", [p["id"] for p in settings.available_providers()])
        settings.set_key("custom", "sk-custom-12345678")
        settings.save({"provider": "custom"})
        self.assertEqual(settings.effective_provider(), "custom")
        self.assertEqual(settings.model_of("custom"), "gpt-4o-mini")

    def test_custom_provider_id_is_deduplicated(self):
        settings.add_provider("Relay", "https://a.example.com/v1", "m1")
        second = settings.add_provider("Relay", "https://b.example.com/v1", "m2")
        self.assertEqual(second["id"], "relay-2")

    def test_remove_custom_provider_clears_key(self):
        settings.add_provider("临时", "https://c.example.com/v1", "m")
        custom_id = [p["id"] for p in settings.list_providers() if not p["builtin"]][0]
        settings.set_key(custom_id, "sk-temp-12345678")
        settings.remove_provider(custom_id)
        self.assertIsNone(settings.provider_config(custom_id))
        self.assertEqual(settings.get_key(custom_id), "")

    def test_reject_builtin_removal_and_bad_custom_fields(self):
        with self.assertRaises(ValueError):
            settings.remove_provider("deepseek")
        with self.assertRaises(ValueError):
            settings.add_provider("", "https://x.example.com", "m")
        with self.assertRaises(ValueError):
            settings.add_provider("x", "ftp://x", "m")
        with self.assertRaises(ValueError):
            settings.add_provider("x", "https://x.example.com", "")


if __name__ == "__main__":
    unittest.main()

"""多模态消息构造测试。"""
import unittest

from backend.llm.messages import build_user_content


class UserContentTest(unittest.TestCase):
    def test_text_only_stays_string(self):
        self.assertEqual(build_user_content("你好", []), "你好")
        self.assertEqual(build_user_content("你好", None), "你好")

    def test_images_become_multimodal_parts(self):
        parts = build_user_content("这是什么", ["data:image/png;base64,AAA"])
        self.assertIsInstance(parts, list)
        self.assertEqual(parts[0], {"type": "text", "text": "这是什么"})
        self.assertEqual(parts[1]["type"], "image_url")
        self.assertTrue(parts[1]["image_url"]["url"].startswith("data:image/png"))

    def test_empty_urls_are_skipped(self):
        parts = build_user_content("看图", ["", "https://example.com/a.png"])
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[1]["image_url"]["url"], "https://example.com/a.png")

    def test_all_empty_images_fall_back_to_string(self):
        self.assertEqual(build_user_content("看图", ["", None]), "看图")


if __name__ == "__main__":
    unittest.main()

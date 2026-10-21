"""SSE 编码测试：保证前端能按空行安全切分事件。"""
import unittest

from backend.engines import streaming


class SseTest(unittest.TestCase):
    def test_format_and_parse_roundtrip(self):
        frame = streaming.format_sse("delta", {"text": "她抬起头"})
        events = streaming.parse_sse(frame)
        self.assertEqual(events, [("delta", {"text": "她抬起头"})])

    def test_multiline_text_does_not_break_frames(self):
        frame = streaming.format_sse("delta", {"text": "第一行\n第二行"})
        # 一段 payload 里不能出现裸换行，否则客户端会把它切成两个事件
        data_line = [line for line in frame.splitlines() if line.startswith("data:")][0]
        self.assertNotIn("\n", data_line)
        events = streaming.parse_sse(frame)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][1]["text"], "第一行\n第二行")

    def test_multiple_frames_parse_in_order(self):
        text = (
            streaming.format_sse("delta", {"text": "你"})
            + streaming.format_sse("delta", {"text": "好"})
            + streaming.format_sse("done", {})
        )
        events = streaming.parse_sse(text)
        self.assertEqual([e[0] for e in events], ["delta", "delta", "done"])
        self.assertEqual("".join(e[1].get("text", "") for e in events), "你好")


if __name__ == "__main__":
    unittest.main()

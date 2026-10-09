import unittest
import numpy as np
from sori.audio import SpeechBuffer
from sori.realtime import Draft, InferenceQueue


class RealtimeTests(unittest.TestCase):
    def test_previews_arrive_before_pause_and_final_audio_is_not_lost(self):
        buffer = SpeechBuffer(16000)
        previews, finals = [], []
        for _ in range(120):
            result = buffer.feed(np.full(800, 0.02, dtype=np.float32))
            if result:
                finals.append(result)
            preview = buffer.preview()
            if preview:
                previews.append(preview)
        self.assertGreaterEqual(len(previews), 6)
        self.assertLessEqual(len(previews[0][0]) / 16000, 0.85)
        self.assertEqual(sum(len(samples) for samples, _ in finals), 96000)

    def test_queue_coalesces_previews_and_prioritizes_final(self):
        queue = InferenceQueue()
        queue.add({"segment": "a", "final": False, "revision": 1})
        self.assertEqual(queue.next()["revision"], 1)
        for revision in range(2, 20):
            queue.add({"segment": "a", "final": False, "revision": revision})
        queue.add({"segment": "a", "final": True})
        queue.add({"segment": "b", "final": False})
        queue.finished()
        self.assertTrue(queue.next()["final"])
        queue.finished()
        self.assertEqual(queue.next()["segment"], "b")
        queue.finished()
        self.assertIsNone(queue.next())

    def test_draft_revisions_and_final_space(self):
        draft = Draft()
        self.assertEqual(draft.change("입력 테스x"), (0, "입력 테스x"))
        self.assertEqual(draft.change("입력 테스트"), (1, "트"))
        self.assertEqual(draft.change("입력 테스트 👋 "), (0, " 👋 "))

    def test_draft_does_not_split_emoji_graphemes(self):
        draft = Draft("메모 👨‍👩‍👧‍👦")
        self.assertEqual(draft.change("메모 👋"), (1, "👋"))


if __name__ == "__main__":
    unittest.main()

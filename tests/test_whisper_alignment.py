from types import SimpleNamespace
import unittest

from app.captions import CaptionCue, caption_segments
from app.whisper_alignment import align_caption_cues, caption_cues_from_segments


class WhisperAlignmentTests(unittest.TestCase):
    def test_whisper_words_become_timed_caption_cues(self):
        segments = [
            SimpleNamespace(
                start=0.0,
                end=1.8,
                text=" Oi, mundo.",
                words=[
                    SimpleNamespace(word=" Oi,", start=0.12, end=0.48),
                    SimpleNamespace(word=" mundo.", start=0.72, end=1.62),
                ],
            )
        ]

        cues = caption_cues_from_segments(segments)
        timed_segments = caption_segments(cues)

        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].text, "Oi, mundo.")
        self.assertAlmostEqual(cues[0].start, 0.12)
        self.assertAlmostEqual(cues[0].end, 1.62)
        self.assertEqual(len(timed_segments), 1)
        self.assertAlmostEqual(timed_segments[0].start, 0.12)
        self.assertAlmostEqual(timed_segments[0].end, 1.62)
        self.assertEqual(timed_segments[0].word_timings[1].start, 0.72)

    def test_whisper_segment_without_words_still_has_fallback_cue(self):
        cues = caption_cues_from_segments([
            SimpleNamespace(start=2.0, end=3.0, text=" fallback", words=None)
        ])

        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].text, "fallback")
        self.assertEqual(cues[0].words, ())

    def test_whisper_timing_keeps_original_script_text(self):
        expected = [CaptionCue(0.0, 2.0, "O rex correu.")]
        segments = [
            SimpleNamespace(
                words=[
                    SimpleNamespace(word="O", start=0.10, end=0.30),
                    SimpleNamespace(word="Hex", start=0.35, end=0.60),
                    SimpleNamespace(word="correu.", start=0.70, end=1.10),
                ]
            )
        ]
        cues = align_caption_cues(expected, segments)
        self.assertEqual(cues[0].text, "O rex correu.")
        self.assertEqual([word.text for word in cues[0].words], ["O", "rex", "correu."])
        self.assertEqual(cues[0].words[1].start, 0.35)
        self.assertEqual(cues[0].words[1].end, 0.60)


if __name__ == "__main__":
    unittest.main()

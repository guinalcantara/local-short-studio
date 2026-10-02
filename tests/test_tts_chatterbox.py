from pathlib import Path
import numpy as np
import tempfile
import unittest
from unittest.mock import Mock

from app.tts_chatterbox import ChatterboxPTBRTTS


class ChatterboxReferenceTests(unittest.TestCase):
    def test_generate_block_sends_full_scene_once_and_does_not_claim_speed_control(self):
        model = Mock()
        model.sr = 24000
        model.generate.return_value = np.ones(2400, dtype=np.float32)
        tts = ChatterboxPTBRTTS(device="cpu")
        tts.model = model

        audio = tts.generate_block("Primeira frase. Segunda frase.", speed=1.2)

        self.assertEqual(len(audio), 2400)
        model.generate.assert_called_once_with(
            "Primeira frase. Segunda frase.",
            language_id="pt",
            exaggeration=0.5,
            cfg_weight=0.5,
            temperature=0.8,
        )

    def test_reference_conditionals_are_prepared_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reference = Path(temp_dir) / "reference.wav"
            reference.write_bytes(b"fake audio")
            model = Mock()
            tts = ChatterboxPTBRTTS(device="cpu", reference_audio_path=reference)

            tts._prepare_reference(model)
            tts._prepare_reference(model)

            model.prepare_conditionals.assert_called_once_with(str(reference), exaggeration=0.5)

    def test_setting_new_reference_invalidates_cached_conditionals(self):
        tts = ChatterboxPTBRTTS(device="cpu")
        tts._reference_loaded_path = "old-reference"

        tts.set_reference_audio("new-reference.wav")

        self.assertEqual(tts.reference_audio_path, Path("new-reference.wav"))
        self.assertIsNone(tts._reference_loaded_path)


if __name__ == "__main__":
    unittest.main()

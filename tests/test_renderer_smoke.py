import math
from pathlib import Path
import shutil
import subprocess
import struct
import json
import tempfile
import unittest
import wave

from app.captions import CaptionCue
from app.renderer import render_video


def write_ppm(path: Path, color: tuple[int, int, int]) -> None:
    width, height = 180, 320
    data = bytearray()
    for y in range(height):
        for x in range(width):
            factor = 0.55 + 0.45 * (y / max(1, height - 1))
            data.extend(min(255, round(channel * factor)) for channel in color)
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + data)


def write_wav(path: Path, seconds: float = 1.25) -> None:
    rate = 24000
    count = round(rate * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for sample in range(count):
            value = int(2500 * math.sin(2 * math.pi * 440 * sample / rate))
            frames.extend(struct.pack("<h", value))
        handle.writeframes(frames)


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg precisa estar instalado para este teste")
class RendererSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.images = [self.root / "one.ppm", self.root / "two.ppm"]
        write_ppm(self.images[0], (25, 85, 190))
        write_ppm(self.images[1], (195, 75, 60))
        self.audio = self.root / "voice.wav"
        write_wav(self.audio)
        self.profile = {
            "width": 270,
            "height": 480,
            "fps": 24,
            "crf": 28,
            "preset": "ultrafast",
            "transition_seconds": 0.15,
            "scene_hold_seconds": 0.2,
            "caption_font_size": 22,
            "caption_margin_vertical": 34,
        }

    def assert_mp4_has_vertical_video_and_audio(self, output: Path):
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height",
                "-of", "json", str(output),
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        streams = json.loads(probe.stdout)["streams"]
        video = next(stream for stream in streams if stream["codec_type"] == "video")
        self.assertEqual((video["width"], video["height"]), (270, 480))
        self.assertTrue(any(stream["codec_type"] == "audio" for stream in streams))

    def tearDown(self):
        self.temp.cleanup()

    def test_short_renders_with_smooth_transition_and_no_captions(self):
        output = self.root / "without_captions.mp4"
        progress_updates = []
        render_video(
            self.images,
            [0.55, 0.55],
            [],
            output,
            profile=self.profile,
            narration_path=self.audio,
            motions=["slow_push_in", "pan_left"],
            captions_enabled=False,
            encoder_mode="libx264",
            progress=lambda message, fraction=None: progress_updates.append((message, fraction)),
        )
        self.assertGreater(output.stat().st_size, 1000)
        self.assert_mp4_has_vertical_video_and_audio(output)
        self.assertFalse(output.with_suffix(".srt").exists())
        self.assertTrue(any("Cena 1/2 renderizada" in message for message, _ in progress_updates))
        self.assertGreaterEqual(progress_updates[-1][1], 0.99)

    def test_short_renders_with_modern_caption_track_burned_in(self):
        output = self.root / "with_captions.mp4"
        render_video(
            self.images,
            [0.55, 0.55],
            [CaptionCue(0.0, 0.5, "Teste de legenda moderna")],
            output,
            profile=self.profile,
            narration_path=self.audio,
            motions=["slow_push_in", "slow_pull_out"],
            captions_enabled=True,
            caption_font="Inter",
            encoder_mode="libx264",
            assets_dir=self.root / "assets",
        )
        self.assertGreater(output.stat().st_size, 1000)
        self.assert_mp4_has_vertical_video_and_audio(output)
        self.assertIn("Teste de legenda moderna", output.with_suffix(".srt").read_text(encoding="utf-8"))

    def test_short_renders_without_image_effects_but_keeps_transition(self):
        output = self.root / "without_image_effects.mp4"
        progress_updates = []
        render_video(
            self.images,
            [0.55, 0.55],
            [],
            output,
            profile=self.profile,
            narration_path=self.audio,
            motions=["slow_push_in", "pan_left"],
            captions_enabled=False,
            encoder_mode="libx264",
            image_effects_enabled=False,
            progress=lambda message, fraction=None: progress_updates.append((message, fraction)),
        )
        self.assertGreater(output.stat().st_size, 1000)
        self.assert_mp4_has_vertical_video_and_audio(output)
        self.assertTrue(any("imagem estática" in message for message, _ in progress_updates))


if __name__ == "__main__":
    unittest.main()

import math
from array import array
from pathlib import Path
import shutil
import subprocess
import struct
import json
import tempfile
import unittest
import wave
from unittest.mock import patch

from app.captions import CaptionCue, CaptionWord
from app.music_catalog import calculate_catalog_gain, measure_integrated_lufs
from app.renderer import (
    RenderScene,
    RenderShot,
    RenderTransition,
    bounded_music_fades,
    render_video,
    resolve_transitions,
)


def write_ppm(path: Path, color: tuple[int, int, int]) -> None:
    width, height = 180, 320
    data = bytearray()
    for y in range(height):
        for x in range(width):
            factor = 0.55 + 0.45 * (y / max(1, height - 1))
            data.extend(min(255, round(channel * factor)) for channel in color)
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + data)


def write_wav(
    path: Path,
    seconds: float = 1.25,
    *,
    amplitude: int = 2500,
    frequency: float = 440.0,
) -> None:
    rate = 24000
    count = round(rate * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for sample in range(count):
            value = int(amplitude * math.sin(2 * math.pi * frequency * sample / rate))
            frames.extend(struct.pack("<h", value))
        handle.writeframes(frames)


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg precisa estar instalado para este teste")
class RendererSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.all_images = [self.root / f"scene_{index}.ppm" for index in range(4)]
        for path, color in zip(
            self.all_images,
            ((25, 85, 190), (195, 75, 60), (35, 175, 75), (210, 180, 30)),
        ):
            write_ppm(path, color)
        self.images = self.all_images[:2]
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
            "caption_height_percent": 45,
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

    def frame_rgb(self, output: Path, timestamp: float) -> tuple[float, float, float]:
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(timestamp),
                "-i", str(output), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
            ],
            capture_output=True,
            check=True,
        )
        pixels = result.stdout
        channels = [pixels[index::3] for index in range(3)]
        return tuple(sum(channel) / len(channel) for channel in channels)

    def video_duration(self, output: Path) -> float:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(output)],
            text=True,
            capture_output=True,
            check=True,
        )
        return float(json.loads(probe.stdout)["format"]["duration"])

    def stream_durations(self, output: Path) -> dict[str, float]:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration",
                "-of", "json", str(output),
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        return {
            stream["codec_type"]: float(stream["duration"])
            for stream in json.loads(probe.stdout)["streams"]
            if stream.get("duration") is not None
        }

    def audio_band_rms(
        self,
        output: Path,
        frequency: float,
        start: float,
        duration: float,
    ) -> float:
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(start),
                "-t", str(duration), "-i", str(output), "-vn",
                "-af", f"bandpass=f={frequency}:width_type=h:w=70",
                "-ac", "1", "-ar", "48000", "-f", "f32le", "-",
            ],
            capture_output=True,
            check=True,
        )
        samples = array("f")
        samples.frombytes(result.stdout)
        return math.sqrt(sum(sample * sample for sample in samples) / max(1, len(samples)))

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
            [
                CaptionCue(
                    0.0,
                    0.5,
                    "Teste de legenda moderna",
                    words=(
                        CaptionWord("Teste", 0.0, 0.16),
                        CaptionWord("de", 0.16, 0.27),
                        CaptionWord("legenda", 0.27, 0.39),
                        CaptionWord("moderna", 0.39, 0.5),
                    ),
                )
            ],
            output,
            profile=self.profile,
            narration_path=self.audio,
            motions=["slow_push_in", "slow_pull_out"],
            captions_enabled=True,
            caption_font="Montserrat",
            caption_font_size=30,
            caption_height_percent=55,
            encoder_mode="libx264",
            assets_dir=self.root / "assets",
        )
        self.assertGreater(output.stat().st_size, 1000)
        self.assert_mp4_has_vertical_video_and_audio(output)
        srt_text = output.with_suffix(".srt").read_text(encoding="utf-8")
        self.assertIn("TESTE DE LEGENDA", srt_text)
        self.assertIn("MODERNA", srt_text)
        ass = output.with_suffix(".ass")
        self.assertTrue(ass.exists())
        ass_text = ass.read_text(encoding="utf-8-sig")
        self.assertIn("Style: Caption,Montserrat,30", ass_text)
        self.assertIn("PlayResX: 270", ass_text)
        self.assertIn("PlayResY: 480", ass_text)
        self.assertIn("\\b800", ass_text)
        self.assertIn("\\an5\\pos(135,216)", ass_text)
        self.assertIn("{\\kf", ass_text)
        self.assertIn("\\fscx72\\fscy72", ass_text)
        self.assertIn("\\alpha&HFF&", ass_text)

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

    def test_two_shots_cut_inside_scene_without_internal_crossfade(self):
        cue = CaptionCue(0.0, 0.9, "Legenda sobre dois planos")
        for captions_enabled in (False, True):
            with self.subTest(captions_enabled=captions_enabled):
                output = self.root / f"two_shots_{captions_enabled}.mp4"
                render_video(
                    [self.images[0]],
                    [1.0],
                    [cue],
                    output,
                    profile=self.profile,
                    narration_path=self.audio,
                    motions=["static"],
                    scene_timelines=[
                        RenderScene(
                            (
                                RenderShot(self.images[0], 0.5, "static"),
                                RenderShot(self.images[1], 0.5, "static"),
                            )
                        )
                    ],
                    captions_enabled=captions_enabled,
                    encoder_mode="libx264",
                    image_effects_enabled=False,
                    assets_dir=self.root / "assets",
                )

                before = self.frame_rgb(output, 0.42)
                after = self.frame_rgb(output, 0.58)
                self.assertGreater(before[2], before[0] * 1.5)
                self.assertGreater(after[0], after[2] * 1.5)
                self.assertAlmostEqual(
                    self.video_duration(output),
                    1.2,
                    delta=1 / self.profile["fps"] + 0.03,
                )
                self.assertEqual(output.with_suffix(".srt").exists(), captions_enabled)

    def test_mixed_cut_crossfade_and_fade_black_preserve_timeline(self):
        output = self.root / "mixed_transitions.mp4"
        transitions = [
            RenderTransition("cut", 0.0, True, "cena_01", "cena_02"),
            RenderTransition("crossfade", 0.15, True, "cena_02", "cena_03"),
            RenderTransition("fade_black", 0.15, True, "cena_03", "cena_04"),
        ]
        render_video(
            self.all_images,
            [0.5, 0.5, 0.5, 0.5],
            [],
            output,
            profile=self.profile,
            narration_path=self.audio,
            motions=["static"] * 4,
            transitions=transitions,
            captions_enabled=False,
            encoder_mode="libx264",
            image_effects_enabled=False,
        )

        before_cut = self.frame_rgb(output, 0.42)
        after_cut = self.frame_rgb(output, 0.54)
        during_crossfade = self.frame_rgb(output, 1.08)
        during_black = self.frame_rgb(output, 1.58)
        after_black = self.frame_rgb(output, 1.72)
        self.assertGreater(before_cut[2], before_cut[0] * 1.5)
        self.assertGreater(after_cut[0], after_cut[2] * 1.5)
        self.assertGreater(during_crossfade[0], 30)
        self.assertGreater(during_crossfade[1], 30)
        self.assertLess(max(during_black), 45)
        self.assertGreater(after_black[0], 100)
        self.assertGreater(after_black[1], 90)
        self.assert_mp4_has_vertical_video_and_audio(output)
        self.assertAlmostEqual(
            self.video_duration(output),
            2.2,
            delta=1 / self.profile["fps"] + 0.03,
        )

    def test_transition_guard_rejects_explicit_duration_and_adjusts_implicit_fade(self):
        scenes = [
            RenderScene((RenderShot(self.images[0], 0.5),), "saida"),
            RenderScene((RenderShot(self.images[1], 0.25),), "entrada"),
        ]
        shortened, notices = resolve_transitions(
            [RenderTransition("crossfade", 0.15, False, "saida", "entrada")],
            scenes,
            default_duration=0.15,
            fps=24,
        )
        self.assertEqual(shortened[0].duration, 3 / 24)
        self.assertIn("encurtada", notices[0])

        replaced, notices = resolve_transitions(
            [RenderTransition("crossfade", 0.15, False, "saida", "entrada_curta")],
            [scenes[0], RenderScene((RenderShot(self.images[1], 0.08),), "entrada_curta")],
            default_duration=0.15,
            fps=24,
        )
        self.assertEqual(replaced[0].type, "cut")
        self.assertIn("substituída por corte", notices[0])

        with self.assertRaisesRegex(ValueError, "Fronteira saida → entrada"):
            resolve_transitions(
                [RenderTransition("crossfade", 0.15, True, "saida", "entrada")],
                scenes,
                default_duration=0.15,
                fps=24,
            )


    def test_music_volume_is_applied_and_clamped_in_final_mix(self):
        with patch("app.renderer._run") as run:
            render_video(
                self.images,
                [0.55, 0.55],
                [],
                self.root / "music_volume.mp4",
                profile=self.profile,
                narration_path=self.audio,
                motions=["static", "static"],
                captions_enabled=False,
                music_path=self.audio,
                music_volume=1.5,
                encoder_mode="libx264",
            )

        final_command = run.call_args.args[0]
        filter_complex = final_command[final_command.index("-filter_complex") + 1]
        self.assertIn("volume=1.000", filter_complex)

    def test_catalog_music_uses_bounded_fades_trim_and_limiter(self):
        self.assertEqual(bounded_music_fades(0.65, 0.5, 0.8), (0.25, 0.4))
        with patch("app.renderer._run") as run:
            render_video(
                self.images,
                [0.2, 0.25],
                [],
                self.root / "catalog_music.mp4",
                profile=self.profile,
                narration_path=self.audio,
                motions=["static", "static"],
                captions_enabled=False,
                music_path=self.audio,
                music_volume=0.025,
                music_fade_in_seconds=0.5,
                music_fade_out_seconds=0.8,
                encoder_mode="libx264",
            )

        final_command = run.call_args.args[0]
        filter_complex = final_command[final_command.index("-filter_complex") + 1]
        self.assertIn("atrim=duration=1.0000", filter_complex)
        self.assertIn("afade=t=in", filter_complex)
        self.assertIn("afade=t=out", filter_complex)
        self.assertIn("normalize=0", filter_complex)
        self.assertIn("alimiter=limit=0.95", filter_complex)

    def test_catalog_mp3_mix_loops_fades_and_tracks_two_voice_levels(self):
        music_wav = self.root / "music_source.wav"
        music_mp3 = self.root / "music_source.mp3"
        loud_voice = self.root / "voice_loud.wav"
        quiet_voice = self.root / "voice_quiet.wav"
        write_wav(music_wav, 1.0, amplitude=12000, frequency=1000.0)
        write_wav(loud_voice, 2.25, amplitude=6000, frequency=440.0)
        write_wav(quiet_voice, 2.25, amplitude=1200, frequency=440.0)
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(music_wav),
                "-codec:a", "libmp3lame", "-q:a", "3", str(music_mp3),
            ],
            check=True,
        )

        music_lufs = measure_integrated_lufs(music_mp3)
        loud_gain = calculate_catalog_gain(12, measure_integrated_lufs(loud_voice), music_lufs)
        quiet_gain = calculate_catalog_gain(12, measure_integrated_lufs(quiet_voice), music_lufs)
        self.assertLess(quiet_gain, loud_gain)

        def mixed_output(name: str, voice: Path, gain: float) -> Path:
            output = self.root / name
            render_video(
                [self.images[0]],
                [2.0],
                [],
                output,
                profile=self.profile,
                narration_path=voice,
                motions=["static"],
                captions_enabled=False,
                music_path=music_mp3,
                music_volume=gain,
                music_fade_in_seconds=0.5,
                music_fade_out_seconds=0.8,
                encoder_mode="libx264",
                image_effects_enabled=False,
            )
            return output

        loud_output = mixed_output("catalog_loud.mp4", loud_voice, loud_gain)
        quiet_output = mixed_output("catalog_quiet.mp4", quiet_voice, quiet_gain)
        muted_output = mixed_output("catalog_muted.mp4", loud_voice, 0.0)

        loud_music_mid = self.audio_band_rms(loud_output, 1000.0, 1.20, 0.08)
        quiet_music_mid = self.audio_band_rms(quiet_output, 1000.0, 1.20, 0.08)
        muted_music_mid = self.audio_band_rms(muted_output, 1000.0, 1.20, 0.08)
        loud_voice_mid = self.audio_band_rms(loud_output, 440.0, 1.20, 0.08)
        music_start = self.audio_band_rms(loud_output, 1000.0, 0.02, 0.08)
        music_end = self.audio_band_rms(loud_output, 1000.0, 2.10, 0.08)

        self.assertGreater(loud_music_mid, muted_music_mid * 2.0)
        self.assertLess(quiet_music_mid, loud_music_mid)
        self.assertLess(loud_music_mid, loud_voice_mid)
        self.assertLess(music_start, loud_music_mid)
        self.assertLess(music_end, loud_music_mid)
        self.assertAlmostEqual(self.video_duration(loud_output), 2.2, delta=0.06)
        self.assertAlmostEqual(self.video_duration(quiet_output), 2.2, delta=0.06)
        durations = self.stream_durations(loud_output)
        self.assertLessEqual(
            abs(durations["video"] - durations["audio"]),
            1 / self.profile["fps"] + 0.03,
        )


if __name__ == "__main__":
    unittest.main()

from io import BytesIO
from pathlib import Path
import os
import numpy as np
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock
import wave
import zipfile

from PIL import Image

from app.pipeline import ShortPipeline, _build_voice_track, project_transitions
from app.captions import CaptionCue, CaptionWord
from app.image_archive import ImageZipError
from app.schemas import Scene, SceneTransition, Shot, VideoProject
from app.whisper_alignment import WhisperTranscript


def zip_with_images() -> bytes:
    archive_bytes = BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        for name, color in (
            ("gancho.png", "blue"),
            ("contexto.png", "red"),
            ("fechamento.png", "green"),
        ):
            image_bytes = BytesIO()
            Image.new("RGB", (32, 48), color).save(image_bytes, format="PNG")
            archive.writestr(name, image_bytes.getvalue())
    return archive_bytes.getvalue()


class PipelineZipTests(unittest.TestCase):
    def test_configured_fade_without_duration_uses_profile_default(self):
        project = VideoProject(
            title="Duração padrão",
            scenes=[
                Scene(
                    id="gancho",
                    narration="Primeira fala.",
                    image_path="gancho.png",
                    transition_to_next=SceneTransition(type="fade_black"),
                ),
                Scene(id="contexto", narration="Segunda fala.", image_path="contexto.png"),
            ],
        )

        transition = project_transitions(project, 0.35)[0]

        self.assertEqual((transition.type, transition.duration), ("fade_black", 0.35))
        self.assertFalse(transition.duration_explicit)

    def test_voice_track_generates_one_natural_block_per_scene(self):
        project = VideoProject(
            title="Bloco natural",
            scenes=[
                Scene(
                    id="gancho",
                    narration="Primeira frase. Segunda frase sem corte artificial.",
                    image_path="gancho.png",
                )
            ],
        )
        tts = Mock()
        tts.generate_block.return_value = np.ones(24000, dtype=np.float32)
        with tempfile.TemporaryDirectory() as temp_dir:
            narration_path, cues, durations = _build_voice_track(
                tts, project, Path(temp_dir), 0.15, lambda *_args: None
            )

        tts.generate_block.assert_called_once_with(
            "Primeira frase. Segunda frase sem corte artificial.",
            voice=project.voice,
            speed=project.speech_speed,
        )
        tts.release.assert_called_once()
        self.assertTrue(narration_path.name == "narration.wav")
        self.assertEqual(len(cues), 1)
        self.assertEqual(durations, [1.0])
        self.assertEqual(cues[0].end, 1.0)

    def test_pipeline_uses_zip_images_without_comfyui(self):
        project = VideoProject(
            title="Teste ZIP",
            scenes=[
                Scene(id="gancho", narration="Primeira fala.", image_path="gancho.png", motion="slow_push_in"),
                Scene(id="contexto", narration="Segunda fala.", image_path="contexto.png", motion="pan_left"),
            ],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            narration = Path(temp_dir) / "narration.wav"
            with wave.open(str(narration), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(24000)
                handle.writeframes(b"\x00\x00" * 2400)

            def fake_voice_track(_tts, _project, audio_dir, _padding, _progress):
                target = Path(audio_dir) / "narration.wav"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(narration.read_bytes())
                return target, [], [0.1, 0.1]

            with patch.dict(os.environ, {"OUTPUT_DIR": temp_dir}), patch("app.pipeline.torch.cuda.is_available", return_value=True), patch(
                "app.pipeline._build_voice_track", side_effect=fake_voice_track
            ), patch("app.pipeline.render_video") as render_video:
                render_video.side_effect = lambda *args, **_kwargs: Path(args[3])
                pipeline = ShortPipeline()
                self.assertFalse(hasattr(pipeline, "comfy"))
                result = pipeline.run(project, zip_with_images())

            image_files = list((result.parent / "images").iterdir())
            self.assertEqual({path.name for path in image_files}, {"gancho.png", "contexto.png"})
            render_video.assert_called_once()
            self.assertEqual(render_video.call_args.kwargs["motions"], ["slow_push_in", "pan_left"])
            self.assertTrue(render_video.call_args.kwargs["image_effects_enabled"])
            transitions = render_video.call_args.kwargs["transitions"]
            self.assertEqual([(item.type, item.duration) for item in transitions], [("crossfade", 0.35)])

    def test_pipeline_can_disable_image_effects(self):
        project = VideoProject(
            title="Teste sem movimentos",
            scenes=[
                Scene(
                    id="gancho",
                    narration="Primeira fala.",
                    image_path="gancho.png",
                    motion="slow_push_in",
                    transition_to_next=SceneTransition(type="cut"),
                ),
                Scene(id="contexto", narration="Segunda fala.", image_path="contexto.png", motion="pan_left"),
            ],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            narration = Path(temp_dir) / "narration.wav"
            with wave.open(str(narration), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(24000)
                handle.writeframes(b"\x00\x00" * 2400)

            def fake_voice_track(_tts, _project, audio_dir, _padding, _progress):
                target = Path(audio_dir) / "narration.wav"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(narration.read_bytes())
                return target, [], [0.1, 0.1]

            with patch.dict(os.environ, {"OUTPUT_DIR": temp_dir}), patch("app.pipeline.torch.cuda.is_available", return_value=True), patch(
                "app.pipeline._build_voice_track", side_effect=fake_voice_track
            ), patch("app.pipeline.WhisperAligner") as whisper_aligner, patch("app.pipeline.render_video") as render_video:
                render_video.side_effect = lambda *args, **_kwargs: Path(args[3])
                ShortPipeline(image_effects_enabled=False).run(project, zip_with_images())

            self.assertEqual(render_video.call_args.kwargs["motions"], ["slow_push_in", "pan_left"])
            self.assertFalse(render_video.call_args.kwargs["image_effects_enabled"])
            self.assertEqual(render_video.call_args.kwargs["transitions"][0].type, "cut")
            whisper_aligner.assert_not_called()

    def test_pipeline_stores_chatterbox_voice_reference_in_run(self):
        project = VideoProject(
            title="Teste voz clonada",
            scenes=[
                Scene(
                    id="gancho",
                    narration="Primeira fala.",
                    image_path="gancho.png",
                    motion="static",
                ),
                Scene(id="contexto", narration="Segunda fala.", image_path="contexto.png", motion="static"),
            ],
        )
        reference = b"RIFF" + (b"reference" * 32)
        with tempfile.TemporaryDirectory() as temp_dir:
            narration = Path(temp_dir) / "narration.wav"
            with wave.open(str(narration), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(24000)
                handle.writeframes(b"\x00\x00" * 2400)

            def fake_voice_track(_tts, _project, audio_dir, _padding, _progress):
                target = Path(audio_dir) / "narration.wav"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(narration.read_bytes())
                return target, [], [0.1, 0.1]

            with patch.dict(os.environ, {"OUTPUT_DIR": temp_dir}), patch("app.pipeline.torch.cuda.is_available", return_value=True), patch(
                "app.pipeline._build_voice_track", side_effect=fake_voice_track
            ), patch("app.pipeline.render_video") as render_video:
                render_video.side_effect = lambda *args, **_kwargs: Path(args[3])
                pipeline = ShortPipeline(tts_engine="chatterbox_ptbr")
                result = pipeline.run(
                    project,
                    zip_with_images(),
                    voice_reference=reference,
                    voice_reference_name="minha_voz.wav",
                )

            saved_reference = result.parent / "audio" / "voice_reference.wav"
            self.assertEqual(saved_reference.read_bytes(), reference)
            self.assertEqual(pipeline.tts.reference_audio_path, saved_reference)

    def test_pipeline_replaces_estimated_cues_with_whisper_cues(self):
        project = VideoProject(
            title="Teste Whisper",
            scenes=[
                Scene(
                    id="gancho",
                    narration="Primeira fala. Segunda ideia.",
                    image_path="gancho.png",
                    motion="static",
                    shots=[
                        Shot(image_path="gancho.png"),
                        Shot(image_path="contexto.png", start_phrase="Segunda ideia"),
                    ],
                    transition_to_next=SceneTransition(type="fade_black", duration_seconds=0.2),
                ),
                Scene(id="fechamento", narration="Última fala.", image_path="fechamento.png", motion="static"),
            ],
        )
        project.captions.enabled = True
        whisper_cues = [
            CaptionCue(0.0, 1.0, project.scenes[0].narration),
            CaptionCue(1.0, 2.0, project.scenes[1].narration),
        ]
        whisper = Mock()
        whisper.transcribe_with_words.return_value = WhisperTranscript(
            tuple(whisper_cues),
            (
                CaptionWord("Primeira", 0.05, 0.20),
                CaptionWord("fala", 0.20, 0.40),
                CaptionWord("Segunda", 0.50, 0.70),
                CaptionWord("ideia", 0.70, 0.90),
                CaptionWord("Última", 1.05, 1.30),
                CaptionWord("fala", 1.30, 1.60),
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            narration = Path(temp_dir) / "narration.wav"
            with wave.open(str(narration), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(24000)
                handle.writeframes(b"\x00\x00" * 2400)

            def fake_voice_track(_tts, _project, audio_dir, _padding, _progress):
                target = Path(audio_dir) / "narration.wav"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(narration.read_bytes())
                return target, [
                    CaptionCue(0.0, 1.0, "estimada 1"),
                    CaptionCue(1.0, 2.0, "estimada 2"),
                ], [1.0, 1.0]

            with patch.dict(os.environ, {"OUTPUT_DIR": temp_dir}), patch("app.pipeline.torch.cuda.is_available", return_value=True), patch(
                "app.pipeline._build_voice_track", side_effect=fake_voice_track
            ), patch("app.pipeline.WhisperAligner", return_value=whisper), patch("app.pipeline.render_video") as render_video:
                render_video.side_effect = lambda *args, **_kwargs: Path(args[3])
                ShortPipeline(image_effects_enabled=False).run(project, zip_with_images())

            whisper.transcribe_with_words.assert_called_once()
            whisper.release.assert_called_once()
            self.assertEqual(render_video.call_args.args[2], whisper_cues)
            self.assertEqual(render_video.call_args.args[1], [1.0, 1.0])
            transition = render_video.call_args.kwargs["transitions"][0]
            self.assertEqual((transition.type, transition.duration, transition.duration_explicit), ("fade_black", 0.2, True))
            timelines = render_video.call_args.kwargs["scene_timelines"]
            self.assertEqual(
                [[shot.duration for shot in scene.shots] for scene in timelines],
                [[0.5, 0.5], [1.0]],
            )

    def test_pipeline_validates_copies_and_aligns_all_shot_images_without_captions(self):
        project = VideoProject(
            title="Teste planos",
            scenes=[
                Scene(
                    id="gancho",
                    narration="Primeira ideia. Segunda ideia aparece.",
                    image_path="gancho.png",
                    motion="slow_push_in",
                    shots=[
                        Shot(image_path="gancho.png"),
                        Shot(image_path="contexto.png", start_phrase="Segunda ideia", motion="pan_left"),
                    ],
                )
            ],
        )
        whisper = Mock()
        whisper.transcribe_with_words.return_value = WhisperTranscript(
            (CaptionCue(0.0, 1.0, project.scenes[0].narration),),
            (
                CaptionWord("Primeira", 0.05, 0.20),
                CaptionWord("ideia", 0.20, 0.40),
                CaptionWord("Segunda", 0.50, 0.70),
                CaptionWord("ideia", 0.70, 0.85),
                CaptionWord("aparece", 0.85, 0.98),
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            narration = Path(temp_dir) / "source.wav"
            with wave.open(str(narration), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(24000)
                handle.writeframes(b"\x00\x00" * 24000)

            def fake_voice_track(_tts, _project, audio_dir, _padding, _progress):
                target = Path(audio_dir) / "narration.wav"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(narration.read_bytes())
                return target, [CaptionCue(0.0, 1.0, project.scenes[0].narration)], [1.0]

            with patch.dict(os.environ, {"OUTPUT_DIR": temp_dir}), patch(
                "app.pipeline.torch.cuda.is_available", return_value=True
            ), patch("app.pipeline._build_voice_track", side_effect=fake_voice_track), patch(
                "app.pipeline.WhisperAligner", return_value=whisper
            ), patch("app.pipeline.render_video") as render_video:
                render_video.side_effect = lambda *args, **_kwargs: Path(args[3])
                result = ShortPipeline().run(project, zip_with_images())

            self.assertEqual(
                {path.name for path in (result.parent / "images").iterdir()},
                {"01_gancho_shot_01.png", "01_gancho_shot_02.png"},
            )
            whisper.transcribe_with_words.assert_called_once()
            timelines = render_video.call_args.kwargs["scene_timelines"]
            self.assertEqual(len(timelines[0].shots), 2)
            self.assertAlmostEqual(timelines[0].shots[0].duration, 0.5)
            self.assertAlmostEqual(timelines[0].shots[1].duration, 0.5)

    def test_missing_shot_image_stops_before_voice_generation(self):
        project = VideoProject(
            title="Plano ausente",
            scenes=[
                Scene(
                    id="gancho",
                    narration="Primeira ideia. Depois surge o detalhe.",
                    image_path="gancho.png",
                    shots=[
                        Shot(image_path="gancho.png"),
                        Shot(image_path="ausente.png", start_phrase="Depois surge"),
                    ],
                )
            ],
        )
        with patch("app.pipeline._build_voice_track") as voice_track:
            with self.assertRaisesRegex(ImageZipError, "ausentes"):
                ShortPipeline().run(project, zip_with_images())
        voice_track.assert_not_called()


if __name__ == "__main__":
    unittest.main()

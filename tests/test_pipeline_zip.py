from io import BytesIO
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
import wave
import zipfile

from PIL import Image

from app.pipeline import ShortPipeline
from app.schemas import Scene, VideoProject


def zip_with_images() -> bytes:
    archive_bytes = BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        for name, color in (("gancho.png", "blue"), ("contexto.png", "red")):
            image_bytes = BytesIO()
            Image.new("RGB", (32, 48), color).save(image_bytes, format="PNG")
            archive.writestr(name, image_bytes.getvalue())
    return archive_bytes.getvalue()


class PipelineZipTests(unittest.TestCase):
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

    def test_pipeline_can_disable_image_effects(self):
        project = VideoProject(
            title="Teste sem movimentos",
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
                ShortPipeline(image_effects_enabled=False).run(project, zip_with_images())

            self.assertEqual(render_video.call_args.kwargs["motions"], ["slow_push_in", "pan_left"])
            self.assertFalse(render_video.call_args.kwargs["image_effects_enabled"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from io import BytesIO
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave
import zipfile

from PIL import Image

from app.captions import CaptionCue
from app.music_catalog import MusicCatalogError, calculate_catalog_gain
from app.pipeline import ShortPipeline, resolve_music_selection
from app.schemas import VideoProject


TRACK_BYTES = b"fake-mp3-for-pipeline-selection"


def write_catalog(input_root: Path, *, selection_status: str = "editorial_candidate") -> Path:
    track_path = input_root / "music_library" / "faixas" / "testes" / "faixa_teste.mp3"
    track_path.parent.mkdir(parents=True, exist_ok=True)
    track_path.write_bytes(TRACK_BYTES)
    catalog = {
        "version": 1,
        "tracks": [
            {
                "id": "faixa_teste",
                "path": "faixas/testes/faixa_teste.mp3",
                "title": "Faixa teste",
                "artist_candidate": "Autor provisório",
                "duration_seconds": 30.0,
                "category": "testes",
                "best_for_estimate": "testes",
                "measured_lufs": -12.0,
                "recommended_volume_percent": 4,
                "selection_status": selection_status,
                "license_status": "unverified",
                "license_url": None,
                "source_url": None,
                "attribution_text": None,
                "sha256": hashlib.sha256(TRACK_BYTES).hexdigest(),
            }
        ],
    }
    (input_root / "music_library" / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False), encoding="utf-8"
    )
    return track_path


def project_with_soundtrack(volume: int = 4) -> VideoProject:
    return VideoProject(
        title="Teste de trilha",
        soundtrack={"track_id": "faixa_teste", "volume_percent": volume},
        scenes=[{"id": "cena", "narration": "Uma fala de teste.", "image_path": "cena.png"}],
    )


def image_zip() -> bytes:
    image = BytesIO()
    Image.new("RGB", (32, 48), "blue").save(image, format="PNG")
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("cena.png", image.getvalue())
    return archive.getvalue()


def write_tone(path: Path) -> None:
    rate = 24000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for sample in range(rate):
            value = int(4000 * math.sin(2 * math.pi * 440 * sample / rate))
            frames.extend(struct.pack("<h", value))
        handle.writeframes(frames)


class PipelineMusicTests(unittest.TestCase):
    def test_music_precedence_is_explicit_and_project_volume_is_validated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_catalog(root)
            manual = root / "manual.mp3"
            manual.write_bytes(b"manual")
            project = project_with_soundtrack()

            selected = resolve_music_selection(
                project,
                root,
                manual_music_path=manual,
                ui_catalog_track_id="faixa_teste",
            )
            self.assertEqual(selected.source, "ui_upload")
            selected = resolve_music_selection(project, root, ui_catalog_track_id="faixa_teste")
            self.assertEqual(selected.source, "ui_catalog")
            selected = resolve_music_selection(project, root)
            self.assertEqual(selected.source, "json_soundtrack")
            self.assertIsNone(resolve_music_selection(project, root, disable_music=True))

            with self.assertRaisesRegex(MusicCatalogError, "coincidir com o catálogo"):
                resolve_music_selection(project_with_soundtrack(volume=3), root)
            self.assertEqual(
                resolve_music_selection(project_with_soundtrack(volume=0), root).requested_volume_percent,
                0.0,
            )

            legacy = VideoProject(
                title="Legado",
                music_path="manual.mp3",
                scenes=[{"id": "cena", "narration": "Fala.", "image_path": "cena.png"}],
            )
            self.assertEqual(resolve_music_selection(legacy, root).source, "legacy_music_path")

    def test_review_track_stops_before_tts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_catalog(root, selection_status="review_required")
            with patch.dict(os.environ, {"INPUT_DIR": str(root), "OUTPUT_DIR": str(root / "output")}), patch(
                "app.pipeline._build_voice_track"
            ) as voice_track, patch("app.pipeline.KokoroTTS") as kokoro:
                with self.assertRaisesRegex(MusicCatalogError, "não pode ser selecionada"):
                    ShortPipeline().run(project_with_soundtrack(), image_zip())
            voice_track.assert_not_called()
            kokoro.assert_not_called()

    def test_catalog_gain_and_report_are_created_without_changing_project_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "output"
            track_path = write_catalog(root)
            project = project_with_soundtrack()

            def fake_voice_track(_tts, _project, audio_dir, _padding, _progress):
                narration = Path(audio_dir) / "narration.wav"
                write_tone(narration)
                return narration, [CaptionCue(0.0, 1.0, "Uma fala de teste.")], [1.0]

            with patch.dict(os.environ, {"INPUT_DIR": str(root), "OUTPUT_DIR": str(output_root)}), patch(
                "app.pipeline.torch.cuda.is_available", return_value=True
            ), patch("app.pipeline._build_voice_track", side_effect=fake_voice_track), patch(
                "app.pipeline.measure_integrated_lufs", return_value=-20.0
            ) as measure, patch("app.pipeline.render_video") as render_video:
                render_video.side_effect = lambda *args, **_kwargs: Path(args[3])
                result = ShortPipeline(catalog_volume_percent=3).run(project, image_zip())

            measure.assert_called_once()
            render_video.assert_called_once()
            kwargs = render_video.call_args.kwargs
            expected_gain = calculate_catalog_gain(3, -20.0, -12.0)
            self.assertEqual(kwargs["music_path"], track_path.resolve())
            self.assertAlmostEqual(kwargs["music_volume"], expected_gain)
            self.assertEqual(kwargs["music_fade_in_seconds"], 0.5)
            self.assertEqual(kwargs["music_fade_out_seconds"], 0.8)

            report = json.loads((result.parent / "soundtrack_used.json").read_text(encoding="utf-8"))
            self.assertEqual(report["source"], "json_soundtrack")
            self.assertEqual(report["track_id"], "faixa_teste")
            self.assertEqual(report["path"], "music_library/faixas/testes/faixa_teste.mp3")
            self.assertEqual(report["requested_volume_percent"], 3.0)
            self.assertAlmostEqual(report["effective_gain_linear"], expected_gain)
            self.assertNotIn(str(root), json.dumps(report))

            exported = json.loads((result.parent / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(exported["soundtrack"]["volume_percent"], 4)


if __name__ == "__main__":
    unittest.main()

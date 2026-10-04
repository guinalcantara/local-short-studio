import unittest

from pathlib import Path
import tempfile
from app.captions import CaptionCue, caption_segments, srt_timestamp, wrap_caption, write_ass
from app.schemas import SceneTransition, Shot, VideoProject, example_project
from app.renderer import load_profiles
from app.voices import DEFAULT_VOICE, normalize_tts_engine, normalize_voice


class ProjectTests(unittest.TestCase):
    def test_example_project_uses_required_image_paths_and_captions_default_off(self):
        project = example_project()
        self.assertEqual(project.profile, "short_vertical")
        self.assertFalse(project.captions.enabled)
        self.assertGreaterEqual(len(project.scenes), 1)
        self.assertTrue(all(scene.image_path for scene in project.scenes))

    def test_old_json_without_youtube_remains_valid(self):
        project = VideoProject.model_validate(
            {
                "title": "Projeto antigo",
                "profile": "short_vertical",
                "voice": "pf_dora",
                "speech_speed": 1.0,
                "visual_style": "cinematic",
                "captions": {"enabled": False, "theme": "modern_blue"},
                "scenes": [
                    {
                        "id": "cena_01",
                        "narration": "Uma fala curta.",
                        "image_path": "cena_01.png",
                        "motion": "static",
                    }
                ],
            }
        )
        self.assertIsNone(project.youtube)

    def test_youtube_metadata_is_preserved_and_strict(self):
        data = example_project().model_dump()
        data["youtube"] = {
            "default_language": "pt-BR",
            "description": "Descrição futura",
            "tags": ["dinossauros"],
            "category_id": "27",
            "status": {
                "privacy_status": "private",
                "license": "youtube",
                "embeddable": True,
                "public_stats_viewable": True,
                "self_declared_made_for_kids": False,
                "contains_synthetic_media": True,
            },
            "notify_subscribers": True,
            "captions": {"enabled": True, "language": "pt-BR", "format": "vtt"},
        }
        parsed = VideoProject.model_validate(data)
        exported = VideoProject.from_json_text(parsed.to_json())
        self.assertEqual(exported.youtube.description, "Descrição futura")
        with self.assertRaises(ValueError):
            VideoProject.model_validate({**data, "unexpected": True})
        with self.assertRaises(ValueError):
            VideoProject.model_validate({**data, "youtube": {**data["youtube"], "unexpected": True}})

    def test_image_prompt_is_rejected_and_image_path_is_safe_required(self):
        data = example_project().model_dump()
        data["scenes"][0].pop("image_path")
        with self.assertRaises(ValueError):
            VideoProject.model_validate(data)

    def test_scene_accepts_valid_shots_and_preserves_legacy_image_path(self):
        data = example_project().model_dump()
        scene = data["scenes"][0]
        scene["narration"] = "Os braços parecem pequenos. Mas os fósseis contam outra história."
        scene["shots"] = [
            {"image_path": scene["image_path"]},
            {"image_path": "cena_01_detalhe.png", "start_phrase": "mas os fósseis contam", "motion": "pan_left"},
        ]

        project = VideoProject.model_validate(data)

        self.assertEqual(project.scenes[0].shots[0].image_path, project.scenes[0].image_path)
        self.assertEqual(project.scenes[0].shots[1].motion, "pan_left")

    def test_shots_validate_count_first_image_anchors_and_duplicates(self):
        base = example_project().model_dump()
        scene = base["scenes"][0]
        scene["narration"] = "Uma ideia aparece aqui. Outra ideia termina agora."

        invalid_cases = [
            [{"image_path": scene["image_path"]}],
            [
                {"image_path": "outra.png"},
                {"image_path": "detalhe.png", "start_phrase": "Outra ideia"},
            ],
            [
                {"image_path": scene["image_path"], "start_phrase": "Uma ideia"},
                {"image_path": "detalhe.png", "start_phrase": "Outra ideia"},
            ],
            [
                {"image_path": scene["image_path"]},
                {"image_path": scene["image_path"].upper(), "start_phrase": "Outra ideia"},
            ],
            [
                {"image_path": scene["image_path"]},
                {"image_path": "detalhe.png", "start_phrase": "ideia aparece aqui Outra"},
            ],
        ]
        for shots in invalid_cases:
            with self.subTest(shots=shots), self.assertRaises(ValueError):
                VideoProject.model_validate({**base, "scenes": [{**scene, "shots": shots}]})

    def test_shot_anchor_must_be_unique_and_in_narration_order(self):
        base = example_project().model_dump()
        scene = base["scenes"][0]
        scene["narration"] = "A pista surgiu cedo. A pista voltou depois. O final chegou."
        ambiguous = [
            {"image_path": scene["image_path"]},
            {"image_path": "detalhe.png", "start_phrase": "A pista"},
        ]
        with self.assertRaisesRegex(ValueError, "mais de uma vez"):
            VideoProject.model_validate({**base, "scenes": [{**scene, "shots": ambiguous}]})

        out_of_order = [
            Shot(image_path=scene["image_path"]).model_dump(),
            Shot(image_path="final.png", start_phrase="O final chegou").model_dump(),
            Shot(image_path="cedo.png", start_phrase="surgiu cedo").model_dump(),
        ]
        with self.assertRaisesRegex(ValueError, "ordem"):
            VideoProject.model_validate({**base, "scenes": [{**scene, "shots": out_of_order}]})
        data = example_project().model_dump()
        data["scenes"][0]["image_prompt"] = "não deve existir"
        with self.assertRaises(ValueError):
            VideoProject.model_validate(data)
        data = example_project().model_dump()
        data["scenes"][0]["image_path"] = "../cena.png"
        with self.assertRaises(ValueError):
            VideoProject.model_validate(data)
        with self.assertRaises(ValueError):
            Shot(image_path="pasta/plano.png")

    def test_scene_transitions_accept_all_types_and_survive_serialization(self):
        project = VideoProject(
            title="Transições",
            scenes=[
                {
                    "id": "cena_01",
                    "narration": "Primeira cena.",
                    "image_path": "cena_01.png",
                    "transition_to_next": {"type": "cut"},
                },
                {
                    "id": "cena_02",
                    "narration": "Segunda cena.",
                    "image_path": "cena_02.png",
                    "transition_to_next": {"type": "crossfade", "duration_seconds": 0.25},
                },
                {
                    "id": "cena_03",
                    "narration": "Terceira cena.",
                    "image_path": "cena_03.png",
                    "transition_to_next": {"type": "fade_black"},
                },
                {
                    "id": "cena_04",
                    "narration": "Última cena.",
                    "image_path": "cena_04.png",
                },
            ],
        )

        exported = VideoProject.from_json_text(project.to_json())

        self.assertEqual(
            [scene.transition_to_next.type for scene in exported.scenes[:-1]],
            ["cut", "crossfade", "fade_black"],
        )
        self.assertEqual(exported.scenes[1].transition_to_next.duration_seconds, 0.25)
        self.assertIsNone(exported.scenes[2].transition_to_next.duration_seconds)

    def test_scene_transition_rejects_invalid_duration_type_and_extra_fields(self):
        invalid = [
            {"type": "cut", "duration_seconds": 0.2},
            {"type": "crossfade", "duration_seconds": 0.1},
            {"type": "fade_black", "duration_seconds": 0.5},
            {"type": "zoom"},
            {"type": "crossfade", "unexpected": True},
        ]
        for transition in invalid:
            with self.subTest(transition=transition), self.assertRaises(ValueError):
                SceneTransition.model_validate(transition)

    def test_transition_is_rejected_on_last_scene(self):
        with self.assertRaisesRegex(ValueError, "última cena"):
            VideoProject(
                title="Última cena inválida",
                scenes=[
                    {
                        "id": "ultima",
                        "narration": "Fim.",
                        "image_path": "fim.png",
                        "transition_to_next": {"type": "cut"},
                    }
                ],
            )

    def test_voice_selection_has_safe_fallback(self):
        self.assertEqual(normalize_voice("pm_alex"), "pm_alex")
        self.assertEqual(normalize_voice("pm_santa"), "pm_santa")
        self.assertEqual(normalize_voice("idioma-inexistente"), DEFAULT_VOICE)

    def test_tts_engine_selection_has_safe_kokoro_default(self):
        self.assertEqual(normalize_tts_engine("kokoro"), "kokoro")
        self.assertEqual(normalize_tts_engine("chatterbox_ptbr"), "chatterbox_ptbr")
        self.assertEqual(normalize_tts_engine("mecanismo-inexistente"), "kokoro")

    def test_caption_helpers(self):
        wrapped = wrap_caption("Essa é uma frase um pouco comprida para caber numa legenda vertical moderna", max_chars=25)
        self.assertLessEqual(len(wrapped.splitlines()), 2)
        self.assertEqual(srt_timestamp(61.234), "00:01:01,234")

    def test_karaoke_caption_segments_are_short_and_time_ordered(self):
        segments = caption_segments([
            CaptionCue(1.0, 5.0, "Essa legenda deve acompanhar a fala sem ocupar a tela inteira")
        ])
        self.assertGreater(len(segments), 1)
        self.assertAlmostEqual(segments[0].start, 1.0)
        self.assertAlmostEqual(segments[-1].end, 5.0)
        self.assertTrue(all(segment.end > segment.start for segment in segments))
        self.assertTrue(all(len(segment.words) <= 3 for segment in segments))
        self.assertTrue(all(len(wrap_caption(segment.text, max_chars=24).splitlines()) <= 2 for segment in segments))

    def test_ass_captions_use_montserrat_and_configurable_vertical_position(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = write_ass(
                [CaptionCue(0.0, 2.0, "Uma legenda curta")],
                Path(temp_dir) / "captions.ass",
                vertical_position_percent=45,
            )
            content = target.read_text(encoding="utf-8-sig")
        self.assertIn("Style: Caption,Montserrat,72", content)
        self.assertIn("{\\kf", content)
        self.assertIn("PlayResX: 1080", content)
        self.assertIn("\\b800", content)
        self.assertIn("\\an5\\pos(540,1056)", content)
        self.assertIn("UMA", content)
        self.assertIn("LEGENDA", content)
        self.assertIn("CURTA", content)
        self.assertIn("\\fscx72\\fscy72", content)
        self.assertIn("\\alpha&HFF&", content)

    def test_future_landscape_profile_exists_but_is_disabled(self):
        profiles = load_profiles("config/render_profiles.json")
        self.assertEqual((profiles["video_landscape"]["width"], profiles["video_landscape"]["height"]), (1920, 1080))
        self.assertFalse(profiles["video_landscape"]["enabled"])

    def test_motion_rendering_settings_are_internal_to_the_profile(self):
        profiles = load_profiles("config/render_profiles.json")
        vertical = profiles["short_vertical"]
        self.assertEqual(vertical["motion_render_scale"], 2)
        self.assertEqual(vertical["motion_easing"], "quintic")
        self.assertLess(vertical["motion_zoom_amount"], 0.075)
        self.assertLess(vertical["motion_pan_amount"], 0.08)


if __name__ == "__main__":
    unittest.main()

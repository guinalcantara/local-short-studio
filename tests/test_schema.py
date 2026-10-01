import unittest

from app.captions import srt_timestamp, wrap_caption
from app.schemas import VideoProject, example_project
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
        data = example_project().model_dump()
        data["scenes"][0]["image_prompt"] = "não deve existir"
        with self.assertRaises(ValueError):
            VideoProject.model_validate(data)
        data = example_project().model_dump()
        data["scenes"][0]["image_path"] = "../cena.png"
        with self.assertRaises(ValueError):
            VideoProject.model_validate(data)

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

import unittest

from app.captions import CaptionCue, srt_timestamp, wrap_caption
from app.schemas import VideoProject, example_project
from app.renderer import load_profiles


class ProjectTests(unittest.TestCase):
    def test_example_project_is_valid_and_captions_default_off(self):
        project = example_project()
        self.assertEqual(project.profile, "short_vertical")
        self.assertFalse(project.captions.enabled)
        self.assertGreaterEqual(len(project.scenes), 1)

    def test_caption_wrap_limits_to_two_readable_lines(self):
        wrapped = wrap_caption("Essa é uma frase um pouco comprida para caber numa legenda vertical moderna", max_chars=25)
        self.assertLessEqual(len(wrapped.splitlines()), 2)
        self.assertTrue(all(line for line in wrapped.splitlines()))

    def test_srt_timestamp_uses_millisecond_format(self):
        self.assertEqual(srt_timestamp(61.234), "00:01:01,234")

    def test_caption_option_is_parsed(self):
        data = example_project().model_dump()
        data["captions"]["enabled"] = True
        parsed = VideoProject.model_validate(data)
        self.assertTrue(parsed.captions.enabled)

    def test_future_landscape_profile_exists_but_is_disabled(self):
        profiles = load_profiles("config/render_profiles.json")
        self.assertEqual((profiles["video_landscape"]["width"], profiles["video_landscape"]["height"]), (1920, 1080))
        self.assertFalse(profiles["video_landscape"]["enabled"])


if __name__ == "__main__":
    unittest.main()


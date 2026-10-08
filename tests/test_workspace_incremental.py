from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
from PIL import Image

from app.incremental import WorkspacePipeline
from app.schemas import Scene, VideoProject
from app.workspace import ProjectWorkspace


def image_zip(*names: str) -> bytes:
    content = BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        for index, name in enumerate(names):
            image = BytesIO()
            Image.new("RGB", (40, 70), (30 + index * 30, 80, 140)).save(image, format="PNG")
            archive.writestr(name, image.getvalue())
    return content.getvalue()


class FakeTTS:
    def __init__(self):
        self.device = "cpu"
        self.calls: list[str] = []

    def generate_block(self, text, **_kwargs):
        self.calls.append(text)
        return np.full(2_400, 0.1, dtype=np.float32)

    def release(self):
        pass


def fake_render(*args, **_kwargs):
    target = Path(args[3])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"visual")
    return target


def fake_compose(*args, **_kwargs):
    target = Path(args[3])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"final")
    return target


class WorkspaceTests(unittest.TestCase):
    def test_workspace_resumes_effective_project_and_rejects_corrupt_artifact(self):
        project = VideoProject(title="Persistente", scenes=[Scene(id="gancho", narration="Uma fala.", image_path="gancho.png")])
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = ProjectWorkspace.create(project.title, output_root=temp_dir)
            workspace.import_image_zip(image_zip("gancho.png"), project)
            workspace.save_project(project)
            artifact = workspace.put_artifact("audio", "a" * 64, b"wav", suffix=".wav")
            self.assertEqual(ProjectWorkspace.open(workspace.root).load_project(), project)
            self.assertEqual(workspace.build_image_zip(project)[:2], b"PK")
            artifact.write_bytes(b"corrompido")
            self.assertIsNone(workspace.get_artifact("audio", "a" * 64))

    def test_preview_then_full_reuses_scene_audio_and_text_edit_only_regenerates_that_scene(self):
        project = VideoProject(
            title="Cache",
            scenes=[
                Scene(id="primeira", narration="Primeira fala.", image_path="primeira.png"),
                Scene(id="segunda", narration="Segunda fala.", image_path="segunda.png"),
            ],
        )
        fake_tts = FakeTTS()
        with tempfile.TemporaryDirectory() as temp_dir, patch("app.incremental.WorkspacePipeline._new_tts", return_value=fake_tts), patch("app.incremental.render_video", side_effect=fake_render), patch("app.incremental.compose_scene_clips", side_effect=fake_compose):
            workspace = ProjectWorkspace.create(project.title, output_root=temp_dir)
            pipeline = WorkspacePipeline(workspace, disable_music=True)
            archive = image_zip("primeira.png", "segunda.png")
            pipeline.preview(project, archive, resolution=960)
            self.assertEqual(fake_tts.calls, ["Primeira fala."])
            pipeline.run(project, archive)
            self.assertEqual(fake_tts.calls, ["Primeira fala.", "Segunda fala."])
            changed = project.model_copy(deep=True)
            changed.scenes[1].narration = "Segunda fala revisada."
            pipeline.run(changed, archive)
            self.assertEqual(fake_tts.calls, ["Primeira fala.", "Segunda fala.", "Segunda fala revisada."])


if __name__ == "__main__":
    unittest.main()

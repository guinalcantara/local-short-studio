from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import soundfile as sf
import numpy as np
import torch

from app.captions import CaptionCue
from app.comfy_client import ComfyClient
from app.renderer import load_profiles, render_video
from app.schemas import VideoProject
from app.tts import KokoroTTS, SAMPLE_RATE, split_sentences


def slugify(value: str) -> str:
    ascii_text = value.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-") or "projeto"


def _write_audio(audio: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")


def _build_voice_track(tts: KokoroTTS, project: VideoProject, audio_dir: Path, padding_seconds: float, progress):
    cues: list[CaptionCue] = []
    audio_parts: list[np.ndarray] = []
    scene_durations: list[float] = []
    cursor = 0.0
    try:
        for index, scene in enumerate(project.scenes):
            progress(f"Gerando narração {index + 1}/{len(project.scenes)}: {scene.id}", 0.44 + 0.38 * (index / len(project.scenes)))
            scene_audio: list[np.ndarray] = []
            scene_cues: list[CaptionCue] = []
            sentence_cursor = 0.0
            for sentence in split_sentences(scene.narration):
                part = tts.generate_sentence(sentence, voice=project.voice, speed=project.speech_speed)
                duration = len(part) / SAMPLE_RATE
                scene_audio.append(part)
                scene_cues.append(CaptionCue(cursor + sentence_cursor, cursor + sentence_cursor + duration, sentence))
                sentence_cursor += duration
                pause = np.zeros(round(SAMPLE_RATE * 0.12), dtype=np.float32)
                scene_audio.append(pause)
                sentence_cursor += len(pause) / SAMPLE_RATE
            if not scene_audio:
                raise ValueError(f"A cena {scene.id} não tem frases para narrar.")
            combined = np.concatenate(scene_audio)
            _write_audio(combined, audio_dir / f"{scene.id}.wav")
            audio_parts.append(combined)
            scene_durations.append(len(combined) / SAMPLE_RATE)
            cues.extend(scene_cues)
            cursor += scene_durations[-1]
            if index < len(project.scenes) - 1:
                gap = np.zeros(round(SAMPLE_RATE * padding_seconds), dtype=np.float32)
                audio_parts.append(gap)
                cursor += len(gap) / SAMPLE_RATE
        narration_path = audio_dir / "narration.wav"
        _write_audio(np.concatenate(audio_parts), narration_path)
        for index in range(len(scene_durations) - 1):
            scene_durations[index] += padding_seconds
        return narration_path, cues, scene_durations
    finally:
        # An error in any phrase must not leave Kokoro occupying VRAM for the next run.
        tts.release()


class ShortPipeline:
    def __init__(self, progress=None):
        self.progress = progress or (lambda message, fraction=None: None)
        self.comfy = ComfyClient()
        self.profiles = load_profiles()
        self.output_root = Path(os.getenv("OUTPUT_DIR", "/workspace/output"))
        self.input_root = Path(os.getenv("INPUT_DIR", "/workspace/input"))
        self.tts = KokoroTTS()

    def run(self, project: VideoProject) -> Path:
        profile = self.profiles.get(project.profile)
        if not profile:
            raise ValueError(f"Perfil não encontrado: {project.profile}")
        if not profile.get("enabled", False):
            raise ValueError(f"O perfil '{project.profile}' está reservado para uma fase futura.")

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_dir = self.output_root / f"{slugify(project.title)}_{run_id}"
        image_dir = project_dir / "images"
        audio_dir = project_dir / "audio"
        image_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)
        project_path = project_dir / "project.json"
        project_path.write_text(project.to_json() + "\n", encoding="utf-8")
        (project_dir / "narration.txt").write_text(project.narration_text() + "\n", encoding="utf-8")

        comfy_ok, comfy_message = self.comfy.health()
        if not comfy_ok:
            raise RuntimeError(comfy_message)
        self.progress(comfy_message, 0.02)

        image_paths: list[Path] = []
        image_width = int(os.getenv("IMAGE_WIDTH", "512"))
        image_height = int(os.getenv("IMAGE_HEIGHT", "896"))
        steps = int(os.getenv("IMAGE_STEPS", "18"))
        cfg = float(os.getenv("IMAGE_CFG", "6.5"))
        checkpoint = os.getenv("CHECKPOINT_NAME", "sd-v1-5-pruned-emaonly-fp16.safetensors")
        for index, scene in enumerate(project.scenes):
            self.progress(f"Gerando imagem {index + 1}/{len(project.scenes)}: {scene.id}", 0.04 + 0.36 * (index / len(project.scenes)))
            if scene.image_path:
                supplied = Path(scene.image_path)
                if not supplied.is_absolute():
                    supplied = self.input_root / supplied
                if not supplied.exists():
                    raise FileNotFoundError(f"Imagem informada na cena {scene.id} não existe: {supplied}")
                target = image_dir / f"{scene.id}{supplied.suffix.lower()}"
                shutil.copy2(supplied, target)
                image_paths.append(target)
            else:
                target = image_dir / f"{scene.id}.png"
                self.comfy.generate_image(
                    f"{project.visual_style}, {scene.image_prompt}" if project.visual_style else scene.image_prompt,
                    target,
                    checkpoint=checkpoint,
                    width=image_width,
                    height=image_height,
                    steps=steps,
                    cfg=cfg,
                    seed=scene.seed,
                )
                image_paths.append(target)

        # Release the SD checkpoint before Kokoro loads onto the same 6 GB GPU.
        self.progress("Liberando VRAM do modelo de imagem…", 0.42)
        self.comfy.free_memory()
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA não está disponível para o TTS. Confira driver, WSL 2 e Docker Desktop.")

        padding_seconds = float(profile.get("audio_padding_seconds", 0.15))
        narration_path, cues, scene_durations = _build_voice_track(
            self.tts, project, audio_dir, padding_seconds, self.progress
        )

        self.progress("Aplicando movimentos suaves, transições e formato Short…", 0.86)
        video_path = project_dir / f"{slugify(project.title)}.mp4"
        music_path = project.music_path
        if music_path:
            music_candidate = Path(music_path)
            if not music_candidate.is_absolute():
                music_candidate = self.input_root / music_candidate
            if not music_candidate.exists():
                raise FileNotFoundError(f"Arquivo de música não encontrado: {music_candidate}")
            music_path = str(music_candidate)

        output_video = render_video(
            image_paths,
            scene_durations,
            cues,
            video_path,
            profile=profile,
            narration_path=narration_path,
            motions=[scene.motion for scene in project.scenes],
            captions_enabled=project.captions.enabled,
            music_path=music_path,
            caption_font=os.getenv("CAPTION_FONT", "Inter"),
        )
        self.progress("Short renderizado.", 1.0)
        return output_video

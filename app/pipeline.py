from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import soundfile as sf
from typing import BinaryIO

import numpy as np
import torch

from app.captions import CaptionCue
from app.image_archive import ImageZipValidation, validate_image_zip
from app.renderer import load_profiles, render_video
from app.schemas import VideoProject
from app.tts import KokoroTTS, SAMPLE_RATE, split_sentences
from app.tts_chatterbox import ChatterboxPTBRTTS
from app.voices import normalize_tts_engine, tts_engine_label


VOICE_REFERENCE_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg"}
VOICE_REFERENCE_MAX_BYTES = 25 * 1024 * 1024


def slugify(value: str) -> str:
    ascii_text = value.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-") or "projeto"


def _write_audio(audio: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")


def _write_voice_reference(reference_audio: bytes | bytearray | memoryview, filename: str | None, audio_dir: Path) -> Path:
    data = bytes(reference_audio)
    if not data:
        raise ValueError("O audio de referencia esta vazio.")
    if len(data) > VOICE_REFERENCE_MAX_BYTES:
        raise ValueError("O audio de referencia deve ter no maximo 25 MB.")
    suffix = Path(filename or "voice_reference.wav").suffix.lower()
    if suffix not in VOICE_REFERENCE_EXTENSIONS:
        allowed = ", ".join(sorted(VOICE_REFERENCE_EXTENSIONS))
        raise ValueError(f"Formato de audio de referencia invalido. Use: {allowed}.")
    target = audio_dir / f"voice_reference{suffix}"
    target.write_bytes(data)
    return target


def _build_voice_track(tts, project: VideoProject, audio_dir: Path, padding_seconds: float, progress):
    cues: list[CaptionCue] = []
    audio_parts: list[np.ndarray] = []
    scene_durations: list[float] = []
    cursor = 0.0
    try:
        total_scenes = max(1, len(project.scenes))
        for index, scene in enumerate(project.scenes):
            progress(f"Gerando narração {index + 1}/{len(project.scenes)}: {scene.id}", 0.20 + 0.55 * (index / len(project.scenes)))
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
            progress(f"Narracao {index + 1}/{total_scenes} concluida.", 0.18 + 0.54 * ((index + 1) / total_scenes))
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
        tts.release()


class ShortPipeline:
    def __init__(
        self,
        progress=None,
        tts_engine: str = "kokoro",
        chatterbox_settings: dict[str, float] | None = None,
        image_effects_enabled: bool = True,
    ):
        self.progress = progress or (lambda message, fraction=None: None)
        self.profiles = load_profiles()
        self.output_root = Path(os.getenv("OUTPUT_DIR", "/workspace/output"))
        self.input_root = Path(os.getenv("INPUT_DIR", "/workspace/input"))
        self.tts_engine = normalize_tts_engine(tts_engine)
        self.image_effects_enabled = bool(image_effects_enabled)
        if self.tts_engine == "kokoro":
            self.tts = KokoroTTS()
        else:
            self.tts = ChatterboxPTBRTTS(**(chatterbox_settings or {}))

    def run(
        self,
        project: VideoProject,
        image_zip: bytes | bytearray | memoryview | str | Path | BinaryIO,
        *,
        voice_reference: bytes | bytearray | memoryview | None = None,
        voice_reference_name: str | None = None,
    ) -> Path:
        profile = self.profiles.get(project.profile)
        if not profile:
            raise ValueError(f"Perfil não encontrado: {project.profile}")
        if not profile.get("enabled", False):
            raise ValueError(f"O perfil '{project.profile}' está reservado para uma fase futura.")

        self.progress("Validando imagens do ZIP…", 0.05)
        image_validation: ImageZipValidation = validate_image_zip(
            image_zip,
            [scene.image_path for scene in project.scenes],
        )
        self.progress(
            f"{image_validation.image_count} imagens encontradas; {len(project.scenes)} cenas mapeadas.",
            0.14,
        )

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_dir = self.output_root / f"{slugify(project.title)}_{run_id}"
        image_dir = project_dir / "images"
        audio_dir = project_dir / "audio"
        image_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)
        project_path = project_dir / "project.json"
        project_path.write_text(project.to_json() + "\n", encoding="utf-8")
        (project_dir / "narration.txt").write_text(project.narration_text() + "\n", encoding="utf-8")

        if voice_reference is not None:
            if self.tts_engine != "chatterbox_ptbr":
                raise ValueError("O audio de referencia so pode ser usado com Chatterbox PT-BR.")
            reference_path = _write_voice_reference(voice_reference, voice_reference_name, audio_dir)
            self.tts.set_reference_audio(reference_path)

        image_paths: list[Path] = []
        for scene in project.scenes:
            image = image_validation.image_for(scene.image_path)
            target = image_dir / f"{scene.id}{Path(image.basename).suffix.lower()}"
            target.write_bytes(image.data)
            image_paths.append(target)

        if getattr(self.tts, "device", "cuda") == "cuda" and not torch.cuda.is_available():
            if self.tts_engine != "kokoro":
                raise RuntimeError(
                    f"CUDA nao esta disponivel para {tts_engine_label(self.tts_engine)}. "
                    "Confira driver, WSL 2 e Docker Desktop."
                )
            raise RuntimeError("CUDA não está disponível para o Kokoro. Confira driver, WSL 2 e Docker Desktop.")

        padding_seconds = float(profile.get("audio_padding_seconds", 0.15))
        self.progress(
            f"Preparando {tts_engine_label(self.tts_engine)}; a primeira execucao pode baixar os pesos...",
            0.16,
        )
        narration_path, cues, scene_durations = _build_voice_track(
            self.tts, project, audio_dir, padding_seconds, self.progress
        )

        render_message = (
            "Aplicando movimentos suaves, transições e formato Short…"
            if self.image_effects_enabled
            else "Aplicando transições e formato Short, sem movimentos nas imagens…"
        )
        self.progress(render_message, 0.86)
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
            image_effects_enabled=self.image_effects_enabled,
            captions_enabled=project.captions.enabled,
            music_path=music_path,
            caption_font=os.getenv("CAPTION_FONT", "Inter"),
            progress=self.progress,
        )
        self.progress("Short renderizado.", 1.0)
        return output_video

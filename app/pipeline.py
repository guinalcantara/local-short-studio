from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import soundfile as sf
from typing import BinaryIO

import numpy as np
import torch

from app.captions import CaptionCue, CaptionWord
from app.image_archive import ImageZipValidation, validate_image_zip
from app.renderer import RenderScene, RenderShot, RenderTransition, load_profiles, render_video
from app.schemas import VideoProject
from app.tts import KokoroTTS, SAMPLE_RATE
from app.tts_chatterbox import ChatterboxPTBRTTS
from app.voices import normalize_tts_engine, tts_engine_label
from app.whisper_alignment import WhisperAligner, anchor_start_time


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
            narration = scene.narration.strip()
            if not narration:
                raise ValueError(f"A cena {scene.id} não tem texto para narrar.")
            combined = tts.generate_block(narration, voice=project.voice, speed=project.speech_speed)
            if not len(combined):
                raise RuntimeError(f"O mecanismo de voz não produziu áudio para a cena {scene.id}.")
            duration = len(combined) / SAMPLE_RATE
            _write_audio(combined, audio_dir / f"{scene.id}.wav")
            audio_parts.append(combined)
            scene_durations.append(duration)
            cues.append(CaptionCue(cursor, cursor + duration, narration))
            cursor += scene_durations[-1]
            progress(f"Narracao {index + 1}/{total_scenes} concluida.", 0.18 + 0.54 * ((index + 1) / total_scenes))
            if index < len(project.scenes) - 1:
                gap = np.zeros(round(SAMPLE_RATE * padding_seconds), dtype=np.float32)
                audio_parts.append(gap)
                gap_duration = len(gap) / SAMPLE_RATE
                cursor += gap_duration
                scene_durations[-1] += gap_duration
        narration_path = audio_dir / "narration.wav"
        _write_audio(np.concatenate(audio_parts), narration_path)
        return narration_path, cues, scene_durations
    finally:
        tts.release()


def project_image_paths(project: VideoProject) -> list[str]:
    """Return every visual image once per plan, without duplicating scene.image_path."""
    return [shot.image_path for scene in project.scenes for shot in scene.visual_shots()]


def project_transitions(project: VideoProject, default_duration: float) -> list[RenderTransition]:
    transitions: list[RenderTransition] = []
    for index, scene in enumerate(project.scenes[:-1]):
        target = project.scenes[index + 1]
        configured = scene.transition_to_next
        if configured is None:
            transitions.append(
                RenderTransition("crossfade", default_duration, False, scene.id, target.id)
            )
        elif configured.type == "cut":
            transitions.append(RenderTransition("cut", 0.0, False, scene.id, target.id))
        else:
            transitions.append(
                RenderTransition(
                    configured.type,
                    configured.duration_seconds or default_duration,
                    configured.duration_seconds is not None,
                    scene.id,
                    target.id,
                )
            )
    return transitions


def _build_render_timelines(
    project: VideoProject,
    copied_images: list[list[Path]],
    scene_durations: list[float],
    scene_cues: list[CaptionCue],
    observed_words: tuple[CaptionWord, ...],
    *,
    fps: int,
) -> list[RenderScene]:
    if not (
        len(project.scenes) == len(copied_images) == len(scene_durations) == len(scene_cues)
    ):
        raise ValueError("Cenas, imagens, áudio e cues precisam ter a mesma quantidade.")

    timelines: list[RenderScene] = []
    minimum_frames = 3
    for scene, images, scene_duration, cue in zip(
        project.scenes, copied_images, scene_durations, scene_cues
    ):
        shots = scene.visual_shots()
        if len(images) != len(shots):
            raise ValueError(f"Cena {scene.id}: a quantidade de imagens copiadas não corresponde aos planos.")
        if scene.shots is None:
            timelines.append(RenderScene((RenderShot(images[0], scene_duration, scene.motion),), scene.id))
            continue

        starts = [cue.start]
        for shot_index, shot in enumerate(shots[1:], start=1):
            assert shot.start_phrase is not None
            starts.append(
                anchor_start_time(
                    scene.narration,
                    shot.start_phrase,
                    observed_words,
                    scene_start=cue.start,
                    scene_end=cue.end,
                    scene_id=scene.id,
                    shot_index=shot_index,
                )
            )
        visual_end = cue.start + scene_duration
        boundaries = starts + [visual_end]
        durations: list[float] = []
        for shot_index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
            frames = round((end - start) * fps)
            if end <= start or frames < minimum_frames:
                phrase = shots[shot_index].start_phrase or "início da cena"
                raise ValueError(
                    f"Cena {scene.id}, plano {shot_index + 1}, frase {phrase!r}: "
                    f"a duração visual ficou menor que {minimum_frames} frames; ajuste o roteiro ou a âncora"
                )
            durations.append(end - start)
        timelines.append(
            RenderScene(
                tuple(
                    RenderShot(image, duration, shot.motion or scene.motion)
                    for image, duration, shot in zip(images, durations, shots)
                ),
                scene.id,
            )
        )
    return timelines


class ShortPipeline:
    def __init__(
        self,
        progress=None,
        tts_engine: str = "kokoro",
        chatterbox_settings: dict[str, float] | None = None,
        image_effects_enabled: bool = True,
        music_volume: float = 0.12,
    ):
        self.progress = progress or (lambda message, fraction=None: None)
        self.profiles = load_profiles()
        self.output_root = Path(os.getenv("OUTPUT_DIR", "/workspace/output"))
        self.input_root = Path(os.getenv("INPUT_DIR", "/workspace/input"))
        self.tts_engine = normalize_tts_engine(tts_engine)
        self.image_effects_enabled = bool(image_effects_enabled)
        self.music_volume = min(1.0, max(0.0, float(music_volume)))
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
        required_image_paths = project_image_paths(project)
        image_validation: ImageZipValidation = validate_image_zip(
            image_zip,
            required_image_paths,
        )
        plan_count = len(required_image_paths)
        self.progress(
            f"{image_validation.image_count} imagens encontradas; "
            f"{len(project.scenes)} cenas e {plan_count} planos mapeados.",
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

        copied_images: list[list[Path]] = []
        for scene_index, scene in enumerate(project.scenes):
            scene_images: list[Path] = []
            for shot_index, shot in enumerate(scene.visual_shots()):
                image = image_validation.image_for(shot.image_path)
                suffix = Path(image.basename).suffix.lower()
                target_name = (
                    f"{scene.id}{suffix}"
                    if scene.shots is None
                    else f"{scene_index + 1:02d}_{scene.id}_shot_{shot_index + 1:02d}{suffix}"
                )
                target = image_dir / target_name
                target.write_bytes(image.data)
                scene_images.append(target)
            copied_images.append(scene_images)
        image_paths = [images[0] for images in copied_images]

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
        narration_path, scene_cues, scene_durations = _build_voice_track(
            self.tts, project, audio_dir, padding_seconds, self.progress
        )
        cues = scene_cues
        observed_words: tuple[CaptionWord, ...] = ()
        has_multiple_shots = any(scene.shots is not None for scene in project.scenes)
        if project.captions.enabled or has_multiple_shots:
            reason = "planos e legendas" if project.captions.enabled and has_multiple_shots else (
                "planos" if has_multiple_shots else "legendas"
            )
            self.progress(f"Sincronizando {reason} palavra por palavra com Whisper…", 0.76)
            aligner = WhisperAligner()
            try:
                transcript = aligner.transcribe_with_words(narration_path, expected_cues=scene_cues)
                cues = list(transcript.cues)
                observed_words = transcript.observed_words
            finally:
                aligner.release()
            self.progress(f"{len(cues)} blocos sincronizados pelo Whisper.", 0.84)

        scene_timelines = None
        if has_multiple_shots:
            scene_timelines = _build_render_timelines(
                project,
                copied_images,
                scene_durations,
                scene_cues,
                observed_words,
                fps=int(profile["fps"]),
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
            scene_timelines=scene_timelines,
            transitions=project_transitions(project, float(profile["transition_seconds"])),
            image_effects_enabled=self.image_effects_enabled,
            captions_enabled=project.captions.enabled,
            music_path=music_path,
            music_volume=self.music_volume,
            caption_font=os.getenv("CAPTION_FONT", "Inter"),
            progress=self.progress,
        )
        self.progress("Short renderizado.", 1.0)
        return output_video

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import soundfile as sf
from typing import BinaryIO

import numpy as np
import torch

from app.captions import (
    DEFAULT_CAPTION_FONT,
    CaptionCue,
    CaptionWord,
)
from app.image_archive import ImageZipValidation, validate_image_zip
from app.music_catalog import (
    CatalogTrack,
    MusicCatalog,
    MusicCatalogError,
    calculate_catalog_gain,
    load_music_catalog,
    measure_integrated_lufs,
)
from app.renderer import RenderScene, RenderShot, RenderTransition, load_profiles, render_video
from app.schemas import VideoProject
from app.tts import KokoroTTS, SAMPLE_RATE
from app.tts_chatterbox import ChatterboxPTBRTTS
from app.voices import normalize_tts_engine, tts_engine_label
from app.whisper_alignment import WhisperAligner, anchor_start_time


VOICE_REFERENCE_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg"}
VOICE_REFERENCE_MAX_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class ResolvedMusicSelection:
    path: Path
    source: str
    requested_volume_percent: float
    report_path: str
    track: CatalogTrack | None = None


def _report_music_path(path: Path, input_root: Path) -> str:
    try:
        return path.resolve().relative_to(input_root.resolve()).as_posix()
    except ValueError:
        return path.name


def resolve_music_selection(
    project: VideoProject,
    input_root: str | Path,
    *,
    disable_music: bool = False,
    manual_music_path: str | Path | None = None,
    ui_catalog_track_id: str | None = None,
    ui_catalog_volume_percent: int | None = None,
    legacy_music_volume: float = 0.12,
) -> ResolvedMusicSelection | None:
    """Resolve UI and project music with explicit, testable precedence."""
    root = Path(input_root)
    catalog: MusicCatalog | None = None
    project_track: CatalogTrack | None = None
    if project.soundtrack is not None:
        catalog = load_music_catalog(root)
        project_track = catalog.get(project.soundtrack.track_id, verify_sha256=True)
        if project.soundtrack.volume_percent not in {0, project_track.recommended_volume_percent}:
            raise MusicCatalogError(
                f"O volume_percent de {project_track.id!r} deve ser 0% para silêncio explícito "
                f"ou coincidir com o catálogo: {project_track.recommended_volume_percent}%."
            )

    if disable_music:
        return None

    if manual_music_path is not None:
        path = Path(manual_music_path)
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo de música manual não encontrado: {path}")
        percent = min(100.0, max(0.0, float(legacy_music_volume) * 100.0))
        return ResolvedMusicSelection(
            path.resolve(), "ui_upload", percent, _report_music_path(path, root)
        )

    if ui_catalog_track_id is not None:
        catalog = catalog or load_music_catalog(root)
        track = catalog.get(ui_catalog_track_id, verify_sha256=True)
        requested = (
            track.recommended_volume_percent
            if ui_catalog_volume_percent is None
            else ui_catalog_volume_percent
        )
        if isinstance(requested, bool) or not isinstance(requested, int) or not 0 <= requested <= 12:
            raise MusicCatalogError("O volume escolhido para a faixa catalogada deve ser inteiro entre 0% e 12%.")
        return ResolvedMusicSelection(
            track.path,
            "ui_catalog",
            float(requested),
            f"music_library/{track.relative_path}",
            track,
        )

    if project_track is not None:
        assert project.soundtrack is not None
        requested = (
            project.soundtrack.volume_percent
            if ui_catalog_volume_percent is None
            else ui_catalog_volume_percent
        )
        if isinstance(requested, bool) or not isinstance(requested, int) or not 0 <= requested <= 12:
            raise MusicCatalogError("O volume escolhido para a faixa catalogada deve ser inteiro entre 0% e 12%.")
        return ResolvedMusicSelection(
            project_track.path,
            "json_soundtrack",
            float(requested),
            f"music_library/{project_track.relative_path}",
            project_track,
        )

    if project.music_path:
        path = Path(project.music_path)
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo de música não encontrado: {path}")
        percent = min(100.0, max(0.0, float(legacy_music_volume) * 100.0))
        return ResolvedMusicSelection(
            path.resolve(), "legacy_music_path", percent, _report_music_path(path, root)
        )
    return None


def _soundtrack_report(
    selection: ResolvedMusicSelection,
    *,
    effective_gain: float,
    voice_lufs: float | None,
) -> dict[str, object]:
    track = selection.track
    return {
        "version": 1,
        "source": selection.source,
        "track_id": track.id if track else None,
        "title": track.title if track else selection.path.name,
        "artist_candidate": track.artist_candidate if track else None,
        "path": selection.report_path,
        "requested_volume_percent": selection.requested_volume_percent,
        "effective_gain_linear": effective_gain,
        "effective_volume_percent": effective_gain * 100.0,
        "voice_measured_lufs": voice_lufs,
        "music_catalog_lufs": track.measured_lufs if track else None,
        "license_status": track.license_status if track else "not_provided",
        "license_url": track.license_url if track else None,
        "source_url": track.source_url if track else None,
        "attribution_text": track.attribution_text if track else None,
    }


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
        disable_music: bool = False,
        manual_music_path: str | Path | None = None,
        catalog_track_id: str | None = None,
        catalog_volume_percent: int | None = None,
        caption_font_size: int | None = None,
        caption_height_percent: float | None = None,
    ):
        self.progress = progress or (lambda message, fraction=None: None)
        self.profiles = load_profiles()
        self.output_root = Path(os.getenv("OUTPUT_DIR", "/workspace/output"))
        self.input_root = Path(os.getenv("INPUT_DIR", "/workspace/input"))
        self.tts_engine = normalize_tts_engine(tts_engine)
        self.chatterbox_settings = chatterbox_settings or {}
        self.image_effects_enabled = bool(image_effects_enabled)
        self.music_volume = min(1.0, max(0.0, float(music_volume)))
        self.disable_music = bool(disable_music)
        self.manual_music_path = manual_music_path
        self.catalog_track_id = catalog_track_id
        self.catalog_volume_percent = catalog_volume_percent
        self.caption_font_size = caption_font_size
        self.caption_height_percent = caption_height_percent
        self.tts = None

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

        self.progress("Validando a seleção de música…", 0.15)
        music_selection = resolve_music_selection(
            project,
            self.input_root,
            disable_music=self.disable_music,
            manual_music_path=self.manual_music_path,
            ui_catalog_track_id=self.catalog_track_id,
            ui_catalog_volume_percent=self.catalog_volume_percent,
            legacy_music_volume=self.music_volume,
        )
        if self.tts_engine == "kokoro":
            self.tts = KokoroTTS()
        else:
            self.tts = ChatterboxPTBRTTS(**self.chatterbox_settings)

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
            assert self.tts is not None
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

        assert self.tts is not None
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
        voice_lufs: float | None = None
        effective_music_gain = self.music_volume
        if music_selection is not None and music_selection.track is not None:
            self.progress("Medindo a intensidade da narração para ajustar a trilha…", 0.75)
            voice_lufs = measure_integrated_lufs(narration_path)
            capped_percent = min(
                music_selection.requested_volume_percent,
                float(music_selection.track.recommended_volume_percent),
            )
            effective_music_gain = calculate_catalog_gain(
                capped_percent,
                voice_lufs,
                music_selection.track.measured_lufs,
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
            music_path=music_selection.path if music_selection else None,
            music_volume=effective_music_gain,
            music_fade_in_seconds=0.5 if music_selection and music_selection.track else None,
            music_fade_out_seconds=0.8 if music_selection and music_selection.track else None,
            caption_font=os.getenv("CAPTION_FONT", DEFAULT_CAPTION_FONT),
            caption_font_size=self.caption_font_size,
            caption_height_percent=self.caption_height_percent,
            progress=self.progress,
        )
        if music_selection is not None:
            report = _soundtrack_report(
                music_selection,
                effective_gain=effective_music_gain,
                voice_lufs=voice_lufs,
            )
            (project_dir / "soundtrack_used.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        self.progress("Short renderizado.", 1.0)
        return output_video

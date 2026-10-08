from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Iterable

import numpy as np
import soundfile as sf
import torch

from app.captions import CaptionCue, CaptionWord, DEFAULT_CAPTION_FONT
from app.music_catalog import calculate_catalog_gain, measure_integrated_lufs
from app.pipeline import (
    ResolvedMusicSelection,
    project_transitions,
    resolve_music_selection,
)
from app.renderer import RenderScene, RenderShot, compose_scene_clips, load_profiles, render_video
from app.schemas import Scene, VideoProject
from app.tts import KokoroTTS, SAMPLE_RATE
from app.tts_chatterbox import ChatterboxPTBRTTS
from app.voices import normalize_tts_engine, tts_engine_label
from app.whisper_alignment import WhisperAligner, WhisperTranscript, anchor_start_time
from app.workspace import ProjectWorkspace, WorkspaceError, file_sha256, fingerprint


AUDIO_PIPELINE_VERSION = "scene-audio-v1"
ALIGNMENT_PIPELINE_VERSION = "scene-whisper-v1"
VISUAL_PIPELINE_VERSION = "scene-visual-v1"
FINAL_PIPELINE_VERSION = "final-compose-v1"
_GPU_LOCK = RLock()


@dataclass(frozen=True)
class PipelineResult:
    video_path: Path
    duration_seconds: float
    preview: bool
    workspace_id: str
    reused_audio_scene_ids: tuple[str, ...]
    music_gain: float | None
    preview_music_may_change: bool = False


def _audio_bytes(audio: np.ndarray) -> bytes:
    buffer = BytesIO()
    sf.write(buffer, np.asarray(audio, dtype=np.float32), SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def _read_audio(path: Path) -> np.ndarray:
    data, rate = sf.read(path, dtype="float32", always_2d=False)
    values = np.asarray(data, dtype=np.float32)
    if values.ndim > 1:
        values = values.mean(axis=1)
    if rate != SAMPLE_RATE and len(values):
        target = round(len(values) * SAMPLE_RATE / rate)
        values = np.interp(
            np.linspace(0.0, 1.0, target, endpoint=False),
            np.linspace(0.0, 1.0, len(values), endpoint=False),
            values,
        ).astype(np.float32)
    return values.reshape(-1)


def _cue_payload(cues: Iterable[CaptionCue], observed_words: Iterable[CaptionWord]) -> bytes:
    payload = {
        "cues": [
            {
                "start": cue.start,
                "end": cue.end,
                "text": cue.text,
                "words": [{"text": word.text, "start": word.start, "end": word.end} for word in cue.words],
            }
            for cue in cues
        ],
        "observed_words": [{"text": word.text, "start": word.start, "end": word.end} for word in observed_words],
    }
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _transcript_from_file(path: Path) -> WhisperTranscript:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        cues = tuple(
            CaptionCue(
                float(item["start"]),
                float(item["end"]),
                str(item["text"]),
                tuple(CaptionWord(str(word["text"]), float(word["start"]), float(word["end"])) for word in item.get("words", [])),
            )
            for item in payload["cues"]
        )
        words = tuple(CaptionWord(str(item["text"]), float(item["start"]), float(item["end"])) for item in payload["observed_words"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise WorkspaceError("O alinhamento salvo está corrompido.") from exc
    return WhisperTranscript(cues, words)


def _shift_cue(cue: CaptionCue, offset: float) -> CaptionCue:
    return CaptionCue(
        cue.start + offset,
        cue.end + offset,
        cue.text,
        tuple(CaptionWord(word.text, word.start + offset, word.end + offset) for word in cue.words),
    )


class WorkspacePipeline:
    """Selective persistent render pipeline used by the editing interface."""

    def __init__(
        self,
        workspace: ProjectWorkspace,
        *,
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
        self.workspace = workspace
        self.progress = progress or (lambda message, fraction=None: None)
        self.profiles = load_profiles()
        self.input_root = Path(os.getenv("INPUT_DIR", "/workspace/input"))
        self.tts_engine = normalize_tts_engine(tts_engine)
        self.chatterbox_settings = dict(chatterbox_settings or {})
        self.image_effects_enabled = bool(image_effects_enabled)
        self.music_volume = min(1.0, max(0.0, float(music_volume)))
        self.disable_music = bool(disable_music)
        self.manual_music_path = manual_music_path
        self.catalog_track_id = catalog_track_id
        self.catalog_volume_percent = catalog_volume_percent
        self.caption_font_size = caption_font_size
        self.caption_height_percent = caption_height_percent

    def _profile(self, project: VideoProject, *, preview_height: int | None = None) -> dict[str, Any]:
        source = self.profiles.get(project.profile)
        if not source or not source.get("enabled", False):
            raise ValueError(f"O perfil '{project.profile}' não está disponível para renderização.")
        profile = dict(source)
        if preview_height is not None:
            if preview_height not in {960, 1920}:
                raise ValueError("A prévia aceita 540×960 ou 1080×1920.")
            scale = preview_height / int(source["height"])
            profile["height"] = preview_height
            profile["width"] = round(int(source["width"]) * scale)
            profile["caption_font_size"] = max(24, round(int(source["caption_font_size"]) * scale))
            profile["caption_margin_vertical"] = max(1, round(int(source.get("caption_margin_vertical", 0)) * scale))
        return profile

    def _settings_payload(self, reference_hash: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tts_engine": self.tts_engine,
            "image_effects_enabled": self.image_effects_enabled,
            "caption_font_size": self.caption_font_size,
            "caption_height_percent": self.caption_height_percent,
            "music_source": "none" if self.disable_music else ("manual" if self.manual_music_path else "catalog_or_json"),
            "catalog_track_id": self.catalog_track_id,
            "catalog_volume_percent": self.catalog_volume_percent,
            "music_volume": self.music_volume,
            "voice_reference_sha256": reference_hash,
        }
        if self.tts_engine == "chatterbox_ptbr":
            payload["chatterbox"] = self.chatterbox_settings
        return payload

    def _new_tts(self, voice_reference_path: Path | None):
        tts = KokoroTTS() if self.tts_engine == "kokoro" else ChatterboxPTBRTTS(**self.chatterbox_settings)
        if getattr(tts, "device", "cuda") == "cuda" and not torch.cuda.is_available():
            raise RuntimeError(f"CUDA não está disponível para {tts_engine_label(self.tts_engine)}.")
        if voice_reference_path is not None:
            if self.tts_engine != "chatterbox_ptbr":
                raise ValueError("Áudio de referência só pode ser usado com Chatterbox PT-BR.")
            tts.set_reference_audio(voice_reference_path)
        return tts

    def _ensure_scene_audio(
        self,
        project: VideoProject,
        reference_path: Path | None,
        reference_hash: str | None,
        force_scene_ids: set[str],
    ) -> tuple[list[Path], tuple[str, ...]]:
        keys: list[str] = []
        paths: list[Path | None] = []
        missing: list[tuple[int, Scene, str]] = []
        reused: list[str] = []
        for index, scene in enumerate(project.scenes):
            realization = self.workspace.new_realization(scene.id) if scene.id in force_scene_ids else self.workspace.active_realization(scene.id)
            identity = {
                "version": AUDIO_PIPELINE_VERSION,
                "text": scene.narration.strip(),
                "engine": self.tts_engine,
                "voice": project.voice if self.tts_engine == "kokoro" else None,
                "speech_speed": project.speech_speed if self.tts_engine == "kokoro" else None,
                "chatterbox": self.chatterbox_settings if self.tts_engine == "chatterbox_ptbr" else None,
                "voice_reference_sha256": reference_hash if self.tts_engine == "chatterbox_ptbr" else None,
                "realization": realization,
            }
            key = fingerprint(identity)
            keys.append(key)
            cached = self.workspace.get_artifact("audio", key)
            paths.append(cached)
            if cached is None:
                missing.append((index, scene, key))
            else:
                reused.append(scene.id)
        if missing:
            self.progress("Gerando somente as narrações alteradas…", 0.20)
            with _GPU_LOCK:
                tts = self._new_tts(reference_path)
                try:
                    for position, scene, key in missing:
                        self.progress(f"Gerando narração {position + 1}/{len(project.scenes)}: {scene.id}", None)
                        audio = tts.generate_block(scene.narration.strip(), voice=project.voice, speed=project.speech_speed)
                        if not len(audio):
                            raise RuntimeError(f"O mecanismo de voz não produziu áudio para a cena {scene.id}.")
                        paths[position] = self.workspace.put_artifact("audio", key, _audio_bytes(audio), suffix=".wav")
                finally:
                    tts.release()
        return [path for path in paths if path is not None], tuple(reused)

    def _ensure_alignments(
        self,
        project: VideoProject,
        audio_paths: list[Path],
        *,
        required: bool,
    ) -> list[WhisperTranscript | None]:
        if not required:
            return [None] * len(project.scenes)
        configuration = {
            "version": ALIGNMENT_PIPELINE_VERSION,
            "model": os.getenv("WHISPER_MODEL", "small"),
            "device": os.getenv("WHISPER_DEVICE", "cuda"),
            "compute_type": os.getenv("WHISPER_COMPUTE_TYPE", "float16"),
        }
        results: list[WhisperTranscript | None] = [None] * len(project.scenes)
        missing: list[tuple[int, str]] = []
        for index, (scene, audio_path) in enumerate(zip(project.scenes, audio_paths)):
            key = fingerprint({**configuration, "audio_sha256": file_sha256(audio_path)})
            cached = self.workspace.get_artifact("alignment", key)
            if cached is None:
                missing.append((index, key))
            else:
                results[index] = _transcript_from_file(cached)
        if missing:
            self.progress("Sincronizando somente as cenas sem alinhamento válido…", 0.72)
            with _GPU_LOCK:
                aligner = WhisperAligner()
                try:
                    for index, key in missing:
                        scene, audio_path = project.scenes[index], audio_paths[index]
                        duration = len(_read_audio(audio_path)) / SAMPLE_RATE
                        transcript = aligner.transcribe_with_words(
                            audio_path,
                            expected_cues=[CaptionCue(0.0, duration, scene.narration.strip())],
                        )
                        stored = self.workspace.put_artifact(
                            "alignment", key, _cue_payload(transcript.cues, transcript.observed_words), suffix=".json"
                        )
                        results[index] = _transcript_from_file(stored)
                finally:
                    aligner.release()
        return results

    def _master_audio(self, audio_paths: list[Path], visual_durations: list[float]) -> Path:
        key = fingerprint({"version": "master-audio-v1", "audio": [file_sha256(path) for path in audio_paths], "durations": visual_durations})
        cached = self.workspace.get_artifact("master_audio", key)
        if cached is not None:
            return cached
        parts: list[np.ndarray] = []
        for index, path in enumerate(audio_paths):
            parts.append(_read_audio(path))
            speech_duration = len(parts[-1]) / SAMPLE_RATE
            padding = max(0.0, visual_durations[index] - speech_duration)
            if padding:
                parts.append(np.zeros(round(SAMPLE_RATE * padding), dtype=np.float32))
        return self.workspace.put_artifact("master_audio", key, _audio_bytes(np.concatenate(parts)), suffix=".wav")

    def _timelines(
        self,
        project: VideoProject,
        audio_paths: list[Path],
        visual_durations: list[float],
        alignments: list[WhisperTranscript | None],
        profile: dict[str, Any],
    ) -> tuple[list[RenderScene], list[CaptionCue]]:
        timelines: list[RenderScene] = []
        all_cues: list[CaptionCue] = []
        offset = 0.0
        fps = int(profile["fps"])
        for index, scene in enumerate(project.scenes):
            speech_duration = len(_read_audio(audio_paths[index])) / SAMPLE_RATE
            transcript = alignments[index]
            if transcript is None:
                local_cues = (CaptionCue(0.0, speech_duration, scene.narration.strip()),)
                observed: tuple[CaptionWord, ...] = ()
            else:
                local_cues, observed = transcript.cues, transcript.observed_words
            all_cues.extend(_shift_cue(cue, offset) for cue in local_cues)
            shots = scene.visual_shots()
            starts = [0.0]
            if scene.shots is not None:
                if transcript is None:
                    raise ValueError(f"Cena {scene.id} precisa de alinhamento para cortar os planos.")
                for shot_index, shot in enumerate(shots[1:], start=1):
                    assert shot.start_phrase is not None
                    starts.append(anchor_start_time(scene.narration, shot.start_phrase, observed, scene_start=0.0, scene_end=speech_duration, scene_id=scene.id, shot_index=shot_index))
            boundaries = starts + [visual_durations[index]]
            rendered: list[RenderShot] = []
            for shot_index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
                if end <= start or round((end - start) * fps) < 3:
                    phrase = shots[shot_index].start_phrase or "início da cena"
                    raise ValueError(f"Cena {scene.id}, plano {shot_index + 1}, frase {phrase!r}: duração menor que 3 frames.")
                shot = shots[shot_index]
                rendered.append(RenderShot(self.workspace.image_path(shot.image_path), end - start, scene.effective_motion(shot), scene.effective_camera(shot)))
            timelines.append(RenderScene(tuple(rendered), scene.id))
            offset += visual_durations[index]
        return timelines, all_cues

    def _ensure_visuals(
        self,
        timelines: list[RenderScene],
        audio_paths: list[Path],
        visual_durations: list[float],
        profile: dict[str, Any],
    ) -> list[Path]:
        visuals: list[Path] = []
        for index, (timeline, audio_path, duration) in enumerate(zip(timelines, audio_paths, visual_durations)):
            timeline_payload = [
                {"image": file_sha256(Path(shot.image_path)), "duration": shot.duration, "motion": shot.motion, "camera": shot.camera.model_dump(mode="json") if shot.camera else None}
                for shot in timeline.shots
            ]
            key = fingerprint({"version": VISUAL_PIPELINE_VERSION, "profile": {key: profile.get(key) for key in ("width", "height", "fps", "crf", "preset", "motion_render_scale", "motion_overscan", "motion_zoom_amount", "motion_pan_amount", "motion_easing")}, "effects": self.image_effects_enabled, "timeline": timeline_payload})
            cached = self.workspace.get_artifact("visual", key)
            if cached is None:
                self.progress(f"Renderizando somente a cena visual alterada: {timeline.scene_id}", None)
                target = self.workspace.root / "cache" / "visual" / f"{key}.mp4"
                local_profile = dict(profile)
                local_profile["scene_hold_seconds"] = 0.0
                local_profile["transition_seconds"] = 0.0
                render_video(
                    [timeline.shots[0].image_path], [duration], [], target,
                    profile=local_profile, narration_path=audio_path, motions=[timeline.shots[0].motion],
                    scene_timelines=[timeline], transitions=[], captions_enabled=False,
                    image_effects_enabled=self.image_effects_enabled, progress=self.progress,
                )
                cached = self.workspace.register_artifact("visual", key, target)
            visuals.append(cached)
        return visuals

    def _music(self, project: VideoProject, narration_path: Path) -> tuple[ResolvedMusicSelection | None, float, float | None]:
        selection = resolve_music_selection(
            project, self.input_root, disable_music=self.disable_music, manual_music_path=self.manual_music_path,
            ui_catalog_track_id=self.catalog_track_id, ui_catalog_volume_percent=self.catalog_volume_percent,
            legacy_music_volume=self.music_volume,
        )
        gain, voice_lufs = self.music_volume, None
        if selection is not None and selection.track is not None:
            voice_lufs = measure_integrated_lufs(narration_path)
            gain = calculate_catalog_gain(min(selection.requested_volume_percent, float(selection.track.recommended_volume_percent)), voice_lufs, selection.track.measured_lufs)
        return selection, gain, voice_lufs

    def _execute(
        self,
        project: VideoProject,
        image_zip: bytes | bytearray | memoryview | str | Path | None,
        *,
        preview_scene_index: int | None,
        preview_height: int | None,
        voice_reference: bytes | bytearray | memoryview | None,
        voice_reference_name: str | None,
        force_regenerate_scene_ids: Iterable[str],
    ) -> PipelineResult:
        if image_zip is not None:
            self.progress("Validando e salvando somente as imagens referenciadas…", 0.05)
            self.workspace.import_image_zip(image_zip, project)
        reference_path, reference_hash = None, None
        if voice_reference is not None:
            reference_path, reference_hash = self.workspace.store_voice_reference(voice_reference_name or "voice_reference.wav", voice_reference)
        elif self.workspace.manifest.get("voice_reference"):
            info = self.workspace.manifest["voice_reference"]
            candidate = self.workspace.root / "private" / f"voice_reference_{info.get('sha256')}{info.get('suffix')}"
            if candidate.is_file() and file_sha256(candidate) == info.get("sha256"):
                reference_path, reference_hash = candidate, str(info["sha256"])
        self.workspace.save_project(project)
        self.workspace.save_execution_settings(self._settings_payload(reference_hash))
        if preview_scene_index is not None:
            if not 0 <= preview_scene_index < len(project.scenes):
                raise ValueError("A cena escolhida para prévia não existe.")
            selected = project.scenes[preview_scene_index]
            project = project.model_copy(update={"scenes": [selected]})
            force_ids = {scene_id for scene_id in force_regenerate_scene_ids if scene_id == selected.id}
        else:
            force_ids = set(force_regenerate_scene_ids)
        profile = self._profile(project, preview_height=preview_height)
        audio_paths, reused = self._ensure_scene_audio(project, reference_path, reference_hash, force_ids)
        padding = 0.0 if preview_scene_index is not None else float(profile.get("audio_padding_seconds", 0.15))
        visual_durations = [max(len(_read_audio(path)) / SAMPLE_RATE + (padding if index < len(audio_paths) - 1 else 0.0), 0.4) for index, path in enumerate(audio_paths)]
        needs_alignment = project.captions.enabled or any(scene.shots is not None for scene in project.scenes)
        alignments = self._ensure_alignments(project, audio_paths, required=needs_alignment)
        master = self._master_audio(audio_paths, visual_durations)
        timelines, cues = self._timelines(project, audio_paths, visual_durations, alignments, profile)
        visuals = self._ensure_visuals(timelines, audio_paths, visual_durations, profile)
        selection, gain, _voice_lufs = self._music(project, master)
        output_payload = {
            "version": FINAL_PIPELINE_VERSION,
            "preview": preview_scene_index is not None,
            "profile": {key: profile.get(key) for key in ("width", "height", "fps", "transition_seconds", "scene_hold_seconds", "caption_font_size", "caption_height_percent")},
            "visuals": [file_sha256(path) for path in visuals], "audio": file_sha256(master),
            "cues": _cue_payload(cues, ()).decode("utf-8"),
            "transitions": [item.__dict__ for item in project_transitions(project, float(profile["transition_seconds"]))],
            "captions": project.captions.model_dump(mode="json"), "caption_size": self.caption_font_size, "caption_height": self.caption_height_percent,
            "music": {"path": selection.report_path if selection else None, "sha256": file_sha256(selection.path) if selection else None, "gain": gain},
        }
        key = fingerprint(output_payload)
        kind = "preview" if preview_scene_index is not None else "final"
        cached = self.workspace.get_artifact(kind, key)
        captions_ready = not project.captions.enabled or (cached is not None and cached.with_suffix(".srt").is_file())
        if cached is None or not captions_ready:
            target = self.workspace.root / "cache" / kind / f"{key}.mp4"
            local_profile = dict(profile)
            if preview_scene_index is not None:
                local_profile["scene_hold_seconds"] = 0.0
            compose_scene_clips(
                visuals, visual_durations, cues, target, profile=local_profile, narration_path=master,
                scene_ids=[scene.scene_id or f"cena_{index + 1}" for index, scene in enumerate(timelines)],
                transitions=[] if preview_scene_index is not None else project_transitions(project, float(profile["transition_seconds"])),
                music_path=selection.path if selection else None, music_volume=gain,
                music_fade_in_seconds=0.5 if selection and selection.track else None,
                music_fade_out_seconds=0.8 if selection and selection.track else None,
                captions_enabled=project.captions.enabled, caption_font=os.getenv("CAPTION_FONT", DEFAULT_CAPTION_FONT),
                caption_font_size=self.caption_font_size, caption_height_percent=self.caption_height_percent,
                progress=self.progress,
            )
            cached = self.workspace.register_artifact(kind, key, target)
        duration = sum(visual_durations) + (0.0 if preview_scene_index is not None else float(profile.get("scene_hold_seconds", 0.0)))
        return PipelineResult(cached, duration, preview_scene_index is not None, self.workspace.workspace_id, reused, gain if selection else None, bool(preview_scene_index is not None and selection is not None and selection.track is not None))

    def preview(self, project: VideoProject, image_zip: bytes | bytearray | memoryview | str | Path | None, *, scene_index: int = 0, resolution: int = 960, voice_reference: bytes | bytearray | memoryview | None = None, voice_reference_name: str | None = None) -> PipelineResult:
        return self._execute(project, image_zip, preview_scene_index=scene_index, preview_height=resolution, voice_reference=voice_reference, voice_reference_name=voice_reference_name, force_regenerate_scene_ids=())

    def run(self, project: VideoProject, image_zip: bytes | bytearray | memoryview | str | Path | None, *, voice_reference: bytes | bytearray | memoryview | None = None, voice_reference_name: str | None = None, force_regenerate_scene_ids: Iterable[str] = ()) -> PipelineResult:
        return self._execute(project, image_zip, preview_scene_index=None, preview_height=None, voice_reference=voice_reference, voice_reference_name=voice_reference_name, force_regenerate_scene_ids=force_regenerate_scene_ids)

from __future__ import annotations

import json
from dataclasses import dataclass
import math
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Literal

from PIL import Image, ImageOps

from app.captions import (
    DEFAULT_CAPTION_FONT,
    DEFAULT_CAPTION_ENTRANCE_EFFECT,
    DEFAULT_CAPTION_FONT_SIZE,
    DEFAULT_CAPTION_HEIGHT_PERCENT,
    DEFAULT_CAPTION_UPPERCASE,
    CaptionCue,
    write_ass,
    write_srt,
)
from app.schemas import Camera, CameraPose


MOTIONS = ["slow_push_in", "slow_pull_out", "pan_left", "pan_right", "pan_up", "pan_down", "static"]


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class CameraCrop:
    """A 9:16 crop rectangle in EXIF-corrected source-image coordinates."""

    x: float
    y: float
    width: float
    height: float
    image_width: float
    image_height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class RenderShot:
    image_path: str | Path
    duration: float
    motion: str = "auto"
    camera: Camera | None = None


@dataclass(frozen=True)
class RenderScene:
    shots: tuple[RenderShot, ...]
    scene_id: str | None = None


TransitionKind = Literal["cut", "crossfade", "fade_black"]


@dataclass(frozen=True)
class RenderTransition:
    type: TransitionKind
    duration: float = 0.0
    duration_explicit: bool = False
    source_scene_id: str | None = None
    target_scene_id: str | None = None


def resolve_camera(
    shot_camera: Camera | None,
    scene_camera: Camera | None,
) -> Camera | None:
    """Resolve camera precedence without combining it with legacy motion."""
    return shot_camera if shot_camera is not None else scene_camera


def _positive_finite(value: int | float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} deve ser numérico")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{name} deve ser positivo e finito")
    return numeric


def exif_oriented_dimensions(
    image_width: int | float,
    image_height: int | float,
    exif_orientation: int | None = None,
) -> tuple[float, float]:
    """Return dimensions after the EXIF orientation transform.

    Focus values in the camera contract are always measured in this oriented
    coordinate system. The caller must rasterize with ``ImageOps.exif_transpose``
    (or an equivalent transform) before applying the returned crop to pixels.
    """
    width = _positive_finite(image_width, "image_width")
    height = _positive_finite(image_height, "image_height")
    orientation = 1 if exif_orientation is None else exif_orientation
    if isinstance(orientation, bool) or not isinstance(orientation, int) or not 1 <= orientation <= 8:
        raise ValueError("exif_orientation deve ser um inteiro entre 1 e 8")
    if orientation in {5, 6, 7, 8}:
        return height, width
    return width, height


def minimum_cover_crop(
    image_width: int | float,
    image_height: int | float,
    output_width: int | float,
    output_height: int | float,
    *,
    exif_orientation: int | None = None,
) -> tuple[float, float]:
    """Return the largest source crop with the output aspect ratio.

    This is the zoom=1 reference rectangle: it fills the output without bars
    while retaining as much of the EXIF-corrected image as possible.
    """
    width, height = exif_oriented_dimensions(image_width, image_height, exif_orientation)
    target_width = _positive_finite(output_width, "output_width")
    target_height = _positive_finite(output_height, "output_height")
    target_aspect = target_width / target_height
    image_aspect = width / height
    if image_aspect >= target_aspect:
        return height * target_aspect, height
    return width, width / target_aspect


def quintic_ease(progress: float) -> float:
    """Quintic smoothstep used by the camera contract (zero velocity at ends)."""
    if isinstance(progress, bool) or not isinstance(progress, (int, float)):
        raise ValueError("progress deve ser numérico")
    value = float(progress)
    if not math.isfinite(value):
        raise ValueError("progress deve ser finito")
    value = min(1.0, max(0.0, value))
    return value * value * value * (value * (value * 6.0 - 15.0) + 10.0)


def interpolate_camera_pose(camera: Camera, progress: float) -> CameraPose:
    """Interpolate a validated camera path at a normalized frame position."""
    if camera.easing != "quintic":
        raise ValueError(f"Easing de câmera não suportado: {camera.easing}")
    eased = quintic_ease(progress)

    def interpolate(start: float, end: float) -> float:
        return start + (end - start) * eased

    return CameraPose(
        focus_x=interpolate(camera.start.focus_x, camera.end.focus_x),
        focus_y=interpolate(camera.start.focus_y, camera.end.focus_y),
        zoom=interpolate(camera.start.zoom, camera.end.zoom),
    )


def camera_crop_rect(
    image_width: int | float,
    image_height: int | float,
    output_width: int | float,
    output_height: int | float,
    pose: CameraPose,
    *,
    exif_orientation: int | None = None,
) -> CameraCrop:
    """Map one camera pose to a bounded, aspect-correct crop rectangle.

    ``pose.focus_x``/``focus_y`` are measured after EXIF correction. At image
    edges, the requested focus is limited to the closest crop that remains
    wholly inside available pixels; this is the rectangle the UI should show.
    """
    width, height = exif_oriented_dimensions(image_width, image_height, exif_orientation)
    base_width, base_height = minimum_cover_crop(
        image_width,
        image_height,
        output_width,
        output_height,
        exif_orientation=exif_orientation,
    )
    zoom = pose.zoom
    crop_width = base_width / zoom
    crop_height = base_height / zoom
    max_x = max(0.0, width - crop_width)
    max_y = max(0.0, height - crop_height)
    desired_x = width * pose.focus_x - crop_width / 2.0
    desired_y = height * pose.focus_y - crop_height / 2.0
    x = min(max(desired_x, 0.0), max_x)
    y = min(max(desired_y, 0.0), max_y)
    return CameraCrop(x, y, crop_width, crop_height, width, height)


def camera_crop_for_frame(
    image_width: int | float,
    image_height: int | float,
    output_width: int | float,
    output_height: int | float,
    camera: Camera,
    frame_index: int,
    frame_count: int,
    *,
    exif_orientation: int | None = None,
) -> CameraCrop:
    """Resolve the exact bounded crop for one frame of an explicit camera path."""
    if isinstance(frame_index, bool) or not isinstance(frame_index, int):
        raise ValueError("frame_index deve ser inteiro")
    if isinstance(frame_count, bool) or not isinstance(frame_count, int) or frame_count < 1:
        raise ValueError("frame_count deve ser inteiro positivo")
    if not 0 <= frame_index < frame_count:
        raise ValueError("frame_index deve estar dentro de frame_count")
    progress = 0.0 if frame_count == 1 else frame_index / (frame_count - 1)
    return camera_crop_rect(
        image_width,
        image_height,
        output_width,
        output_height,
        interpolate_camera_pose(camera, progress),
        exif_orientation=exif_orientation,
    )


def resolve_transitions(
    transitions: list[RenderTransition] | None,
    scenes: list[RenderScene],
    *,
    default_duration: float,
    fps: int,
) -> tuple[list[RenderTransition], list[str]]:
    boundary_count = max(0, len(scenes) - 1)
    requested = (
        transitions
        if transitions is not None
        else [RenderTransition("crossfade", default_duration) for _ in range(boundary_count)]
    )
    if len(requested) != boundary_count:
        raise ValueError("A lista de transições precisa corresponder às fronteiras entre cenas.")

    resolved: list[RenderTransition] = []
    notices: list[str] = []
    for index, transition in enumerate(requested):
        source_id = transition.source_scene_id or scenes[index].scene_id or f"cena {index + 1}"
        target_id = transition.target_scene_id or scenes[index + 1].scene_id or f"cena {index + 2}"
        if transition.type == "cut":
            if transition.duration:
                raise ValueError(f"Fronteira {source_id} → {target_id}: corte seco deve ter duração zero.")
            resolved.append(
                RenderTransition("cut", 0.0, transition.duration_explicit, source_id, target_id)
            )
            continue
        if transition.type not in {"crossfade", "fade_black"}:
            raise ValueError(f"Fronteira {source_id} → {target_id}: tipo de transição inválido.")

        duration = transition.duration
        if duration <= 0:
            raise ValueError(
                f"Fronteira {source_id} → {target_id}: fades precisam ter duração positiva."
            )
        requested_frames = max(1, round(duration * fps))
        incoming_first_shot_frames = round(scenes[index + 1].shots[0].duration * fps)
        available_frames = max(0, incoming_first_shot_frames - 3)
        if requested_frames > available_frames:
            if transition.duration_explicit:
                raise ValueError(
                    f"Fronteira {source_id} → {target_id}: a transição de {requested_frames} frames "
                    f"não cabe no primeiro plano de {incoming_first_shot_frames} frames; "
                    "são necessários ao menos 3 frames visíveis depois do efeito"
                )
            if available_frames == 0:
                notices.append(
                    f"Fronteira {source_id} → {target_id}: transição implícita substituída por corte "
                    "para preservar o primeiro plano da cena de entrada."
                )
                resolved.append(RenderTransition("cut", 0.0, False, source_id, target_id))
                continue
            notices.append(
                f"Fronteira {source_id} → {target_id}: transição implícita encurtada de "
                f"{requested_frames} para {available_frames} frames."
            )
            requested_frames = available_frames
        resolved.append(
            RenderTransition(
                transition.type,
                requested_frames / fps,
                transition.duration_explicit,
                source_id,
                target_id,
            )
        )
    return resolved, notices


def _round_shot_durations(shots: tuple[RenderShot, ...], scene_duration: float, fps: int) -> tuple[RenderShot, ...]:
    if not shots:
        raise ValueError("Cada cena precisa ter pelo menos um plano visual.")
    raw_total = sum(max(0.0, float(shot.duration)) for shot in shots)
    if raw_total <= 0:
        raise ValueError("As duracoes dos planos precisam ser positivas.")
    total_frames = max(2, round(scene_duration * fps))
    boundaries = [0]
    elapsed = 0.0
    for shot in shots[:-1]:
        elapsed += max(0.0, float(shot.duration))
        boundaries.append(round(total_frames * elapsed / raw_total))
    boundaries.append(total_frames)
    frame_counts = [right - left for left, right in zip(boundaries, boundaries[1:])]
    if any(frames < 2 for frames in frame_counts):
        raise ValueError("Um plano visual ficou menor que dois frames apos o arredondamento.")
    return tuple(
        RenderShot(shot.image_path, frames / fps, shot.motion, shot.camera)
        for shot, frames in zip(shots, frame_counts)
    )


def load_profiles(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    cfg_path = Path(path or os.getenv("RENDER_PROFILES", "/workspace/config/render_profiles.json"))
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    return data


def resolve_motion(value: str, scene_index: int) -> str:
    if value != "auto":
        return value
    return MOTIONS[scene_index % len(MOTIONS)]


def _quote_filter_path(path: Path) -> str:
    resolved = str(path.resolve()).replace("\\", "/")
    return resolved.replace(":", r"\:").replace("'", r"\'")


def _motion_expressions(
    motion: str,
    frames: int,
    *,
    zoom_amount: float = 0.05,
    pan_amount: float = 0.06,
    easing: str = "quintic",
) -> tuple[str, str, str]:
    # zoompan uses the crop dimensions before output scaling; the source is overscanned.
    # A quintic smoothstep has zero velocity and acceleration at both ends. This avoids
    # the visible jerk that cosine easing can still expose after pixel quantization.
    denominator = max(1, frames - 1)
    normalized = f"(on/{denominator})"
    if easing == "quintic":
        progress = f"(({normalized})*({normalized})*({normalized})*(({normalized})*(({normalized})*6-15)+10))"
    else:
        progress = f"(0.5-0.5*cos(PI*on/{denominator}))"
    center_x = "iw/2-(iw/zoom/2)"
    center_y = "ih/2-(ih/zoom/2)"
    if motion == "slow_push_in":
        return (f"1.0+{zoom_amount}*{progress}", center_x, center_y)
    if motion == "slow_pull_out":
        return (f"1.0+{zoom_amount}*(1-{progress})", center_x, center_y)
    if motion == "pan_left":
        z = f"1.0+{pan_amount}"
        return (z, f"(iw-iw/zoom)*{progress}", center_y)
    if motion == "pan_right":
        z = f"1.0+{pan_amount}"
        return (z, f"(iw-iw/zoom)*(1-{progress})", center_y)
    if motion == "pan_up":
        z = f"1.0+{pan_amount}"
        return (z, center_x, f"(ih-ih/zoom)*{progress}")
    if motion == "pan_down":
        z = f"1.0+{pan_amount}"
        return (z, center_x, f"(ih-ih/zoom)*(1-{progress})")
    return ("1.0", center_x, center_y)


def _run(command: list[str]) -> None:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise RenderError("FFmpeg falhou.\n" + result.stderr[-6000:])


def _render_explicit_camera_clip(
    source: Path,
    output: Path,
    *,
    camera: Camera,
    output_width: int,
    output_height: int,
    fps: int,
    total_frames: int,
    camera_frames: int,
    encoder_mode: str,
    crf: int,
    preset: str,
) -> None:
    """Render a bounded explicit camera path from EXIF-corrected pixels.

    FFmpeg's ``zoompan`` cannot vary the crop width and height while keeping a
    focus expressed in original-image coordinates.  Generating the RGB frames
    here keeps the crop helper used by the UI and the final render identical,
    including at edges.  The camera reaches its last keyframe at the real plan
    duration; any transition/hold frames retain that last framing.
    """
    if total_frames < 1:
        raise ValueError("A câmera precisa de ao menos um frame para renderizar.")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{output_width}x{output_height}", "-framerate", str(fps),
        "-i", "pipe:0", "-frames:v", str(total_frames), "-an",
        *_encoder_args(encoder_mode, crf, preset),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        interpolation_frames = max(1, camera_frames)
        for frame_index in range(total_frames):
            camera_index = min(frame_index, interpolation_frames - 1)
            crop = camera_crop_for_frame(
                image.width,
                image.height,
                output_width,
                output_height,
                camera,
                camera_index,
                interpolation_frames,
            )
            left = max(0, min(image.width - 1, int(math.floor(crop.x))))
            top = max(0, min(image.height - 1, int(math.floor(crop.y))))
            right = max(left + 1, min(image.width, int(math.ceil(crop.right))))
            bottom = max(top + 1, min(image.height, int(math.ceil(crop.bottom))))
            frame = image.crop((left, top, right, bottom)).resize(
                (output_width, output_height), resampling
            )
            assert process.stdin is not None
            process.stdin.write(frame.tobytes())
        assert process.stdin is not None
        process.stdin.close()
        return_code = process.wait()
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        if return_code:
            raise RenderError("FFmpeg falhou ao renderizar a câmera explícita.\n" + stderr[-6000:])
    except Exception:
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        process.kill()
        process.wait()
        raise


def _encoder_args(encoder_mode: str, crf: int, preset: str) -> list[str]:
    mode = encoder_mode.lower()
    if mode == "auto" and shutil.which("ffmpeg"):
        check = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], text=True, capture_output=True)
        if "h264_nvenc" in check.stdout:
            return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", str(crf)]
    if mode == "nvenc":
        check = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], text=True, capture_output=True)
        if "h264_nvenc" not in check.stdout:
            raise RenderError("VIDEO_ENCODER=nvenc, mas h264_nvenc não está disponível neste FFmpeg.")
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", str(crf)]
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]


def bounded_music_fades(
    duration: float,
    fade_in_seconds: float,
    fade_out_seconds: float,
) -> tuple[float, float]:
    """Fit the requested fades inside the final video duration."""
    total = max(0.0, float(duration))
    fade_in = max(0.0, float(fade_in_seconds))
    fade_out = max(0.0, float(fade_out_seconds))
    requested = fade_in + fade_out
    if requested <= 0.0 or total <= 0.0:
        return 0.0, 0.0
    scale = min(1.0, total / requested)
    return fade_in * scale, fade_out * scale


def compose_scene_clips(
    scene_clips: list[str | Path],
    scene_audio_durations: list[float],
    cues: list[CaptionCue],
    output_path: str | Path,
    *,
    profile: dict[str, Any],
    narration_path: str | Path,
    scene_ids: list[str] | None = None,
    transitions: list[RenderTransition] | None = None,
    music_path: str | Path | None = None,
    music_volume: float = 0.12,
    music_fade_in_seconds: float | None = None,
    music_fade_out_seconds: float | None = None,
    captions_enabled: bool = False,
    caption_font: str = DEFAULT_CAPTION_FONT,
    caption_font_size: int | None = None,
    caption_height_percent: float | None = None,
    caption_uppercase: bool | None = None,
    caption_entrance_effect: str | None = None,
    encoder_mode: str | None = None,
    assets_dir: str | Path = "/workspace/assets",
    progress=None,
) -> Path:
    """Compose cached base scene clips without invalidating them for transitions.

    Each cached clip contains only its own visual duration.  Boundary holds are
    added with ``tpad`` here, so changing a transition, caption or soundtrack
    reuses the per-scene visual render unchanged.
    """
    if not scene_clips or len(scene_clips) != len(scene_audio_durations):
        raise ValueError("Os clipes visuais e as durações das cenas precisam corresponder.")
    paths = [Path(path) for path in scene_clips]
    if any(not path.is_file() for path in paths):
        raise FileNotFoundError("Um clipe visual em cache não está disponível.")
    narration = Path(narration_path)
    if not narration.is_file():
        raise FileNotFoundError(f"Narração não encontrada: {narration}")

    width, height, fps = int(profile["width"]), int(profile["height"]), int(profile["fps"])
    default_transition = float(profile["transition_seconds"])
    hold = max(0.0, float(profile.get("scene_hold_seconds", 0.0)))
    crf, preset = int(profile.get("crf", 20)), str(profile.get("preset", "medium"))
    encoder = encoder_mode or os.getenv("VIDEO_ENCODER", "auto")
    scene_durations = [max(float(value), 0.4) for value in scene_audio_durations]
    scenes = [
        RenderScene((RenderShot(path, duration),), (scene_ids or [None] * len(paths))[index])
        for index, (path, duration) in enumerate(zip(paths, scene_durations))
    ]
    resolved, notices = resolve_transitions(transitions, scenes, default_duration=default_transition, fps=fps)
    if progress:
        for notice in notices:
            progress(notice, None)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent / f"{out.stem}_compose_work"
    work.mkdir(parents=True, exist_ok=True)
    padded_paths: list[Path] = []
    for index, path in enumerate(paths):
        extension = resolved[index].duration if index < len(resolved) else hold
        if extension <= 0:
            padded_paths.append(path)
            continue
        padded = work / f"scene_{index:02d}_padded.mp4"
        _run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
            "-vf", f"tpad=stop_mode=clone:stop_duration={extension:.4f}", "-an",
            *_encoder_args(encoder, crf, preset), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(padded),
        ])
        padded_paths.append(padded)
    clip_durations = [
        duration + (resolved[index].duration if index < len(resolved) else hold)
        for index, duration in enumerate(scene_durations)
    ]

    inputs = [argument for path in padded_paths for argument in ("-i", str(path))]
    audio_input_index = len(padded_paths)
    inputs.extend(["-i", str(narration)])
    has_music = bool(music_path and Path(music_path).is_file())
    music_input_index = audio_input_index + 1
    if has_music:
        inputs.extend(["-stream_loop", "-1", "-i", str(music_path)])

    graph: list[str] = [
        f"[{index}:v]settb=AVTB,setpts=PTS-STARTPTS[v{index}]"
        for index in range(len(padded_paths))
    ]
    current_label, elapsed = "v0", clip_durations[0]
    for index in range(1, len(padded_paths)):
        boundary = resolved[index - 1]
        next_label = f"vx{index}"
        if boundary.type == "cut":
            graph.append(f"[{current_label}][v{index}]concat=n=2:v=1:a=0[{next_label}]")
        else:
            effect = "fade" if boundary.type == "crossfade" else "fadeblack"
            graph.append(
                f"[{current_label}][v{index}]xfade=transition={effect}:duration={boundary.duration:.4f}:"
                f"offset={max(0.0, elapsed - boundary.duration):.4f}[{next_label}]"
            )
        current_label = next_label
        elapsed += clip_durations[index] - boundary.duration
    graph.append(f"[{current_label}]fps={fps},format=yuv420p[vbase]")
    video_label = "vbase"
    if captions_enabled:
        resolved_size = int(caption_font_size if caption_font_size is not None else profile.get("caption_font_size", DEFAULT_CAPTION_FONT_SIZE))
        resolved_height = float(caption_height_percent if caption_height_percent is not None else profile.get("caption_height_percent", DEFAULT_CAPTION_HEIGHT_PERCENT))
        uppercase = bool(profile.get("caption_uppercase", DEFAULT_CAPTION_UPPERCASE)) if caption_uppercase is None else bool(caption_uppercase)
        entrance = str(profile.get("caption_entrance_effect", DEFAULT_CAPTION_ENTRANCE_EFFECT)) if caption_entrance_effect is None else caption_entrance_effect
        write_srt(cues, out.with_suffix(".srt"), uppercase=uppercase)
        ass_path = write_ass(
            cues, out.with_suffix(".ass"), font_name=caption_font,
            font_size=max(24, min(160, resolved_size)),
            margin_vertical=int(profile.get("caption_margin_vertical", 250)),
            vertical_position_percent=max(0.0, min(100.0, resolved_height)),
            play_res_x=width, play_res_y=height, uppercase=uppercase, entrance_effect=entrance,
        )
        graph.append(f"[vbase]subtitles='{_quote_filter_path(ass_path)}':fontsdir='{_quote_filter_path(Path(assets_dir) / 'fonts')}'[vcap]")
        video_label = "vcap"

    music_volume = min(1.0, max(0.0, float(music_volume)))
    output_duration = sum(scene_durations) + hold
    if has_music:
        if music_fade_in_seconds is not None or music_fade_out_seconds is not None:
            fade_in, fade_out = bounded_music_fades(output_duration, music_fade_in_seconds or 0.0, music_fade_out_seconds or 0.0)
            fades: list[str] = []
            if fade_in:
                fades.append(f"afade=t=in:st=0:d={fade_in:.4f}")
            if fade_out:
                fades.append(f"afade=t=out:st={max(0.0, output_duration - fade_out):.4f}:d={fade_out:.4f}")
            fade_chain = (",".join(fades) + ",") if fades else ""
            graph.append(
                f"[{audio_input_index}:a]aresample=48000,apad=pad_dur=2[a_voice];"
                f"[{music_input_index}:a]aresample=48000,atrim=duration={output_duration:.4f},asetpts=PTS-STARTPTS,"
                f"volume={music_volume:.6f},{fade_chain}apad=pad_dur=2[a_music];"
                "[a_voice][a_music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95:level=false[aout]"
            )
        else:
            graph.append(
                f"[{audio_input_index}:a]aresample=48000,apad=pad_dur=2[a_voice];"
                f"[{music_input_index}:a]aresample=48000,volume={music_volume:.3f},apad=pad_dur=2[a_music];"
                "[a_voice][a_music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
    else:
        graph.append(f"[{audio_input_index}:a]aresample=48000,apad=pad_dur=2[aout]")
    if progress:
        progress("Montando transições, áudio e legendas…", 0.95)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
        "-filter_complex", ";".join(graph), "-map", f"[{video_label}]", "-map", "[aout]",
        "-t", f"{output_duration:.4f}", *_encoder_args(encoder, crf, preset),
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
    ])
    return out


def render_video(
    image_paths: list[str | Path],
    scene_audio_durations: list[float],
    cues: list[CaptionCue],
    output_path: str | Path,
    *,
    profile: dict[str, Any],
    narration_path: str | Path,
    captions_enabled: bool,
    motions: list[str] | None = None,
    scene_timelines: list[RenderScene] | None = None,
    transitions: list[RenderTransition] | None = None,
    music_path: str | Path | None = None,
    music_volume: float = 0.12,
    music_fade_in_seconds: float | None = None,
    music_fade_out_seconds: float | None = None,
    caption_font: str = DEFAULT_CAPTION_FONT,
    caption_font_size: int | None = None,
    caption_height_percent: float | None = None,
    caption_uppercase: bool | None = None,
    caption_entrance_effect: str | None = None,
    encoder_mode: str | None = None,
    assets_dir: str | Path = "/workspace/assets",
    image_effects_enabled: bool = True,
    progress=None,
) -> Path:
    if not image_paths:
        raise ValueError("Adicione pelo menos uma imagem para montar o vídeo.")
    if len(image_paths) != len(scene_audio_durations):
        raise ValueError("A lista de imagens e a lista de durações precisam ter o mesmo tamanho.")
    if scene_timelines is not None and len(scene_timelines) != len(scene_audio_durations):
        raise ValueError("A timeline visual precisa corresponder às durações das cenas.")
    narration = Path(narration_path)
    if not narration.exists():
        raise FileNotFoundError(f"Narração não encontrada: {narration}")

    width = int(profile["width"])
    height = int(profile["height"])
    fps = int(profile["fps"])
    default_transition = float(profile["transition_seconds"])
    hold = float(profile["scene_hold_seconds"])
    crf = int(profile.get("crf", 20))
    preset = str(profile.get("preset", "medium"))
    motion_render_scale = max(1.0, float(profile.get("motion_render_scale", 2.0)))
    motion_overscan = max(1.0, float(profile.get("motion_overscan", 1.12)))
    motion_zoom_amount = max(0.0, float(profile.get("motion_zoom_amount", 0.05)))
    motion_pan_amount = max(0.0, float(profile.get("motion_pan_amount", 0.06)))
    motion_easing = str(profile.get("motion_easing", "quintic"))
    music_volume = min(1.0, max(0.0, float(music_volume)))
    motion_width = round(width * motion_render_scale)
    motion_height = round(height * motion_render_scale)
    use_encoder = encoder_mode or os.getenv("VIDEO_ENCODER", "auto")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent / f"{out.stem}_render_work"
    work.mkdir(parents=True, exist_ok=True)

    scene_durations = [max(float(value), 0.4) for value in scene_audio_durations]
    clip_paths: list[Path] = []

    selected_motions = motions or ["auto"] * len(image_paths)
    if len(selected_motions) != len(image_paths):
        raise ValueError("A lista de movimentos precisa corresponder às imagens.")
    if scene_timelines is None:
        scene_timelines = [
            RenderScene((RenderShot(path, duration, motion),), f"cena_{index + 1}")
            for index, (path, duration, motion) in enumerate(
                zip(image_paths, scene_durations, selected_motions)
            )
        ]
    rounded_timelines = [
        RenderScene(_round_shot_durations(scene.shots, duration, fps), scene.scene_id)
        for scene, duration in zip(scene_timelines, scene_durations)
    ]
    resolved_transitions, transition_notices = resolve_transitions(
        transitions,
        rounded_timelines,
        default_duration=default_transition,
        fps=fps,
    )
    for notice in transition_notices:
        if progress:
            progress(notice, None)
    transition_durations = [transition.duration for transition in resolved_transitions]
    clip_durations = [
        duration + (transition_durations[index] if index < len(transition_durations) else hold)
        for index, duration in enumerate(scene_durations)
    ]
    timeline_paths = [shot.image_path for scene in rounded_timelines for shot in scene.shots]
    if any(not Path(path).exists() for path in timeline_paths):
        raise FileNotFoundError("Uma ou mais imagens da timeline não foram encontradas.")

    visual_index = 0
    for scene_index, (scene, scene_clip_duration) in enumerate(zip(rounded_timelines, clip_durations)):
        rendered_shots: list[Path] = []
        if progress:
            scene_effect = f"{len(scene.shots)} plano(s)" if image_effects_enabled else "imagem estática"
            progress(
                f"Renderizando cena {scene_index + 1}/{len(rounded_timelines)} "
                f"({scene_effect})...",
                0.86 + 0.09 * (scene_index / len(rounded_timelines)),
            )
        for shot_index, shot in enumerate(scene.shots):
            source = Path(shot.image_path)
            motion_name = resolve_motion(shot.motion, visual_index)
            duration = shot.duration
            camera_frames = max(1, round(duration * fps))
            if shot_index == len(scene.shots) - 1:
                duration += scene_clip_duration - scene_durations[scene_index]
            frames = max(2, round(duration * fps))
            shot_clip = work / f"scene_{scene_index:02d}_shot_{shot_index:02d}.mp4"
            if shot.camera is not None:
                _render_explicit_camera_clip(
                    source,
                    shot_clip,
                    camera=shot.camera,
                    output_width=width,
                    output_height=height,
                    fps=fps,
                    total_frames=frames,
                    camera_frames=camera_frames,
                    encoder_mode=use_encoder,
                    crf=crf,
                    preset=preset,
                )
            elif image_effects_enabled:
                zoom, x_expr, y_expr = _motion_expressions(
                    motion_name,
                    frames,
                    zoom_amount=motion_zoom_amount,
                    pan_amount=motion_pan_amount,
                    easing=motion_easing,
                )
                overscan_w = round(motion_width * motion_overscan)
                overscan_h = round(motion_height * motion_overscan)
                vf = (
                    f"scale={overscan_w}:{overscan_h}:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop={overscan_w}:{overscan_h},"
                    f"zoompan=z='{zoom}':x='{x_expr}':y='{y_expr}':d=1:s={motion_width}x{motion_height}:fps={fps},"
                    f"scale={width}:{height}:flags=lanczos,"
                    f"trim=duration={duration:.4f},setpts=PTS-STARTPTS,format=yuv420p"
                )
            else:
                vf = (
                    f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop={width}:{height},fps={fps},"
                    f"trim=duration={duration:.4f},setpts=PTS-STARTPTS,format=yuv420p"
                )
            if shot.camera is None:
                _run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-loop", "1", "-framerate", str(fps), "-t", f"{duration:.4f}", "-i", str(source),
                    "-vf", vf, "-an", "-t", f"{duration:.4f}", *_encoder_args(use_encoder, crf, preset),
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(shot_clip),
                ])
            rendered_shots.append(shot_clip)
            visual_index += 1

        if len(rendered_shots) == 1:
            scene_clip = rendered_shots[0]
        else:
            scene_clip = work / f"scene_{scene_index:02d}.mp4"
            concat_inputs = [argument for path in rendered_shots for argument in ("-i", str(path))]
            concat_sources = "".join(
                f"[{index}:v]settb=AVTB,setpts=PTS-STARTPTS[v{index}];"
                for index in range(len(rendered_shots))
            )
            concat_labels = "".join(f"[v{index}]" for index in range(len(rendered_shots)))
            concat_graph = f"{concat_sources}{concat_labels}concat=n={len(rendered_shots)}:v=1:a=0[vout]"
            _run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *concat_inputs,
                "-filter_complex", concat_graph, "-map", "[vout]",
                *_encoder_args(use_encoder, crf, preset), "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(scene_clip),
            ])
        clip_paths.append(scene_clip)
        if progress:
            progress(
                f"Cena {scene_index + 1}/{len(rounded_timelines)} renderizada.",
                0.86 + 0.09 * ((scene_index + 1) / len(rounded_timelines)),
            )

    inputs: list[str] = []
    for clip in clip_paths:
        inputs.extend(["-i", str(clip)])
    audio_input_index = len(clip_paths)
    inputs.extend(["-i", str(narration)])
    has_music = bool(music_path and Path(music_path).exists())
    music_input_index = audio_input_index + 1
    if has_music:
        inputs.extend(["-stream_loop", "-1", "-i", str(music_path)])

    graph: list[str] = []
    for index, duration in enumerate(clip_durations):
        graph.append(f"[{index}:v]settb=AVTB,setpts=PTS-STARTPTS[v{index}]")
    current_label = "v0"
    elapsed = clip_durations[0]
    for index in range(1, len(clip_paths)):
        boundary = resolved_transitions[index - 1]
        next_label = f"vx{index}"
        if boundary.type == "cut":
            graph.append(
                f"[{current_label}][v{index}]concat=n=2:v=1:a=0[{next_label}]"
            )
        else:
            effect = "fade" if boundary.type == "crossfade" else "fadeblack"
            offset = max(0.0, elapsed - boundary.duration)
            graph.append(
                f"[{current_label}][v{index}]xfade=transition={effect}:"
                f"duration={boundary.duration:.4f}:offset={offset:.4f}[{next_label}]"
            )
        current_label = next_label
        elapsed += clip_durations[index] - boundary.duration

    graph.append(f"[{current_label}]fps={fps},format=yuv420p[vbase]")
    video_label = "vbase"
    if captions_enabled:
        fonts_dir = Path(assets_dir) / "fonts"
        resolved_caption_font_size = int(
            caption_font_size
            if caption_font_size is not None
            else profile.get("caption_font_size", DEFAULT_CAPTION_FONT_SIZE)
        )
        resolved_caption_height = float(
            caption_height_percent
            if caption_height_percent is not None
            else profile.get("caption_height_percent", DEFAULT_CAPTION_HEIGHT_PERCENT)
        )
        resolved_caption_uppercase = (
            bool(profile.get("caption_uppercase", DEFAULT_CAPTION_UPPERCASE))
            if caption_uppercase is None
            else bool(caption_uppercase)
        )
        resolved_caption_entrance_effect = (
            str(profile.get("caption_entrance_effect", DEFAULT_CAPTION_ENTRANCE_EFFECT))
            if caption_entrance_effect is None
            else caption_entrance_effect
        )
        srt_path = write_srt(
            cues,
            out.with_suffix(".srt"),
            uppercase=resolved_caption_uppercase,
        )
        ass_path = write_ass(
            cues,
            out.with_suffix(".ass"),
            font_name=caption_font,
            font_size=max(24, min(160, resolved_caption_font_size)),
            margin_vertical=int(profile.get("caption_margin_vertical", 250)),
            vertical_position_percent=max(0.0, min(100.0, resolved_caption_height)),
            play_res_x=width,
            play_res_y=height,
            uppercase=resolved_caption_uppercase,
            entrance_effect=resolved_caption_entrance_effect,
        )
        graph.append(
            f"[vbase]subtitles='{_quote_filter_path(ass_path)}':fontsdir='{_quote_filter_path(fonts_dir)}'[vcap]"
        )
        video_label = "vcap"

    if has_music:
        output_duration = sum(scene_durations) + hold
        if music_fade_in_seconds is not None or music_fade_out_seconds is not None:
            fade_in, fade_out = bounded_music_fades(
                output_duration,
                music_fade_in_seconds or 0.0,
                music_fade_out_seconds or 0.0,
            )
            fade_filters = []
            if fade_in > 0.0:
                fade_filters.append(f"afade=t=in:st=0:d={fade_in:.4f}")
            if fade_out > 0.0:
                fade_filters.append(
                    f"afade=t=out:st={max(0.0, output_duration - fade_out):.4f}:d={fade_out:.4f}"
                )
            fade_chain = ",".join(fade_filters)
            if fade_chain:
                fade_chain += ","
            graph.append(
                f"[{audio_input_index}:a]aresample=48000,apad=pad_dur=2[a_voice];"
                f"[{music_input_index}:a]aresample=48000,atrim=duration={output_duration:.4f},"
                f"asetpts=PTS-STARTPTS,volume={music_volume:.6f},{fade_chain}apad=pad_dur=2[a_music];"
                "[a_voice][a_music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                "alimiter=limit=0.95:level=false[aout]"
            )
        else:
            graph.append(
                f"[{audio_input_index}:a]aresample=48000,apad=pad_dur=2[a_voice];"
                f"[{music_input_index}:a]aresample=48000,volume={music_volume:.3f},apad=pad_dur=2[a_music];"
                "[a_voice][a_music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
    else:
        graph.append(f"[{audio_input_index}:a]aresample=48000,apad=pad_dur=2[aout]")

    filter_complex = ";".join(graph)
    if progress:
        progress("Montando transicoes, audio e legendas...", 0.95)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{video_label}]", "-map", "[aout]",
        "-t", f"{sum(scene_durations) + hold:.4f}",
        *_encoder_args(use_encoder, crf, preset),
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(out),
    ])
    if progress:
        progress("Finalizando o arquivo MP4...", 0.99)
    return out

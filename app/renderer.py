from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from app.captions import CaptionCue, write_srt


MOTIONS = ["slow_push_in", "slow_pull_out", "pan_left", "pan_right", "pan_up", "pan_down", "static"]


class RenderError(RuntimeError):
    pass


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


def _motion_expressions(motion: str, frames: int) -> tuple[str, str, str]:
    # zoompan uses the crop dimensions before output scaling; the source is overscanned.
    progress = f"(0.5-0.5*cos(PI*on/{max(1, frames - 1)}))"
    center_x = "iw/2-(iw/zoom/2)"
    center_y = "ih/2-(ih/zoom/2)"
    if motion == "slow_push_in":
        return (f"1.0+0.075*{progress}", center_x, center_y)
    if motion == "slow_pull_out":
        return (f"1.075-0.075*{progress}", center_x, center_y)
    if motion == "pan_left":
        z = "1.08"
        return (z, f"(iw-iw/zoom)*{progress}", center_y)
    if motion == "pan_right":
        z = "1.08"
        return (z, f"(iw-iw/zoom)*(1-{progress})", center_y)
    if motion == "pan_up":
        z = "1.08"
        return (z, center_x, f"(ih-ih/zoom)*{progress}")
    if motion == "pan_down":
        z = "1.08"
        return (z, center_x, f"(ih-ih/zoom)*(1-{progress})")
    return ("1.025", center_x, center_y)


def _run(command: list[str]) -> None:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise RenderError("FFmpeg falhou.\n" + result.stderr[-6000:])


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


def render_video(
    image_paths: list[str | Path],
    scene_audio_durations: list[float],
    cues: list[CaptionCue],
    output_path: str | Path,
    *,
    profile: dict[str, Any],
    narration_path: str | Path,
    motions: list[str] | None = None,
    captions_enabled: bool,
    music_path: str | Path | None = None,
    caption_font: str = "Inter",
    encoder_mode: str | None = None,
    assets_dir: str | Path = "/workspace/assets",
) -> Path:
    if not image_paths:
        raise ValueError("Adicione pelo menos uma imagem para montar o vídeo.")
    if len(image_paths) != len(scene_audio_durations):
        raise ValueError("A lista de imagens e a lista de durações precisam ter o mesmo tamanho.")
    if any(not Path(path).exists() for path in image_paths):
        raise FileNotFoundError("Uma ou mais imagens da timeline não foram encontradas.")
    narration = Path(narration_path)
    if not narration.exists():
        raise FileNotFoundError(f"Narração não encontrada: {narration}")

    width = int(profile["width"])
    height = int(profile["height"])
    fps = int(profile["fps"])
    transition = float(profile["transition_seconds"])
    hold = float(profile["scene_hold_seconds"])
    crf = int(profile.get("crf", 20))
    preset = str(profile.get("preset", "medium"))
    use_encoder = encoder_mode or os.getenv("VIDEO_ENCODER", "auto")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent / "render_work"
    work.mkdir(parents=True, exist_ok=True)

    scene_durations = [max(float(value), 0.4) for value in scene_audio_durations]
    clip_durations = [
        value + (transition if index < len(scene_durations) - 1 else hold)
        for index, value in enumerate(scene_durations)
    ]
    clip_paths: list[Path] = []

    selected_motions = motions or ["auto"] * len(image_paths)
    if len(selected_motions) != len(image_paths):
        raise ValueError("A lista de movimentos precisa corresponder às imagens.")
    for index, (image_path, motion, duration) in enumerate(zip(image_paths, selected_motions, clip_durations)):
        source = Path(image_path)
        motion_name = resolve_motion(motion, index)
        frames = max(2, round(duration * fps))
        zoom, x_expr, y_expr = _motion_expressions(motion_name, frames)
        clip = work / f"scene_{index:02d}.mp4"
        overscan_w = round(width * 1.12)
        overscan_h = round(height * 1.12)
        vf = (
            f"scale={overscan_w}:{overscan_h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={overscan_w}:{overscan_h},"
            f"zoompan=z='{zoom}':x='{x_expr}':y='{y_expr}':d=1:s={width}x{height}:fps={fps},"
            f"trim=duration={duration:.4f},setpts=PTS-STARTPTS,format=yuv420p"
        )
        _run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-framerate", str(fps), "-t", f"{duration:.4f}", "-i", str(source),
            "-vf", vf, "-an", "-t", f"{duration:.4f}", *_encoder_args(use_encoder, crf, preset),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(clip),
        ])
        clip_paths.append(clip)

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
        next_label = f"vx{index}"
        offset = max(0.0, elapsed - transition)
        graph.append(
            f"[{current_label}][v{index}]xfade=transition=fade:duration={transition:.4f}:offset={offset:.4f}[{next_label}]"
        )
        current_label = next_label
        elapsed += clip_durations[index] - transition

    graph.append(f"[{current_label}]fps={fps},format=yuv420p[vbase]")
    video_label = "vbase"
    if captions_enabled:
        srt_path = write_srt(cues, out.with_suffix(".srt"))
        fonts_dir = Path(assets_dir) / "fonts"
        style = (
            f"FontName={caption_font},FontSize={int(profile.get('caption_font_size', 62))},Bold=1,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00101826,BackColour=&H990E1726,"
            "BorderStyle=3,Outline=0,Shadow=0,Alignment=2,"
            f"MarginV={int(profile.get('caption_margin_vertical', 190))},MarginL=105,MarginR=105"
        )
        graph.append(
            f"[vbase]subtitles='{_quote_filter_path(srt_path)}':fontsdir='{_quote_filter_path(fonts_dir)}':force_style='{style}'[vcap]"
        )
        video_label = "vcap"

    if has_music:
        graph.append(
            f"[{audio_input_index}:a]aresample=48000,apad=pad_dur=2[a_voice];"
            f"[{music_input_index}:a]aresample=48000,volume=0.12,apad=pad_dur=2[a_music];"
            "[a_voice][a_music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
    else:
        graph.append(f"[{audio_input_index}:a]aresample=48000,apad=pad_dur=2[aout]")

    filter_complex = ";".join(graph)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{video_label}]", "-map", "[aout]",
        "-t", f"{sum(scene_durations) + hold:.4f}",
        *_encoder_args(use_encoder, crf, preset),
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(out),
    ])
    return out

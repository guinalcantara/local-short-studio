from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class CaptionCue:
    start: float
    end: float
    text: str


def srt_timestamp(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    whole, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{whole:02},{millis:03}"


def wrap_caption(text: str, max_chars: int = 30) -> str:
    words = re.sub(r"\s+", " ", text).strip().split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    return "\n".join(lines)


def write_srt(cues: list[CaptionCue], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for i, cue in enumerate(cues, start=1):
        if cue.end <= cue.start:
            continue
        blocks.append(
            f"{i}\n{srt_timestamp(cue.start)} --> {srt_timestamp(cue.end)}\n{wrap_caption(cue.text)}"
        )
    target.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return target


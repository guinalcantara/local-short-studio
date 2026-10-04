from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


DEFAULT_CAPTION_FONT = "Montserrat"
DEFAULT_CAPTION_FONT_WEIGHT = 800
DEFAULT_CAPTION_FONT_SIZE = 72
DEFAULT_CAPTION_HEIGHT_PERCENT = 45
CAPTION_MAX_WORDS = 3
DEFAULT_CAPTION_UPPERCASE = True
DEFAULT_CAPTION_ENTRANCE_EFFECT = "pop"


@dataclass
class CaptionWord:
    text: str
    start: float
    end: float


@dataclass
class CaptionCue:
    start: float
    end: float
    text: str
    words: tuple[CaptionWord, ...] = ()


@dataclass(frozen=True)
class CaptionSegment:
    start: float
    end: float
    words: tuple[str, ...]
    word_timings: tuple[CaptionWord, ...] = ()

    @property
    def text(self) -> str:
        return " ".join(self.words)


def srt_timestamp(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    whole, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{whole:02},{millis:03}"


def _ass_timestamp(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, centiseconds = divmod(centiseconds, 360_000)
    minutes, centiseconds = divmod(centiseconds, 6_000)
    whole, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02}:{whole:02}.{centiseconds:02}"


def _word_weight(word: str) -> int:
    letters = re.sub(r"[^\wÀ-ÿ]", "", word, flags=re.UNICODE)
    return max(1, len(letters))


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


def _would_exceed_lines(words: list[str], max_chars: int, max_lines: int) -> bool:
    lines = 1
    line_length = 0
    for word in words:
        if line_length and line_length + 1 + len(word) > max_chars:
            lines += 1
            line_length = len(word)
        else:
            line_length += len(word) if not line_length else 1 + len(word)
    return lines > max_lines


def caption_segments(
    cues: list[CaptionCue],
    *,
    max_chars_per_line: int = 24,
    max_words: int = CAPTION_MAX_WORDS,
) -> list[CaptionSegment]:
    """Split sentence cues into short, time-estimated karaoke caption groups."""
    segments: list[CaptionSegment] = []
    for cue in cues:
        timed_words = tuple(cue.words)
        words = tuple(word.text for word in timed_words) if timed_words else tuple(re.findall(r"\S+", cue.text))
        if cue.end <= cue.start or not words:
            continue
        groups: list[tuple[str, ...]] = []
        current: list[str] = []
        for word in words:
            candidate = current + [word]
            if current and (len(candidate) > max_words or _would_exceed_lines(candidate, max_chars_per_line, 2)):
                groups.append(tuple(current))
                current = [word]
            else:
                current = candidate
        if current:
            groups.append(tuple(current))

        if timed_words:
            timed_index = 0
            for group in groups:
                group_timed_words = timed_words[timed_index:timed_index + len(group)]
                timed_index += len(group)
                if not group_timed_words:
                    continue
                segments.append(
                    CaptionSegment(
                        max(cue.start, group_timed_words[0].start),
                        min(cue.end, group_timed_words[-1].end),
                        group,
                        group_timed_words,
                    )
                )
            continue

        total_weight = sum(_word_weight(word) for word in words)
        cursor = cue.start
        cue_duration = cue.end - cue.start
        consumed_weight = 0
        for group_index, group in enumerate(groups):
            group_weight = sum(_word_weight(word) for word in group)
            consumed_weight += group_weight
            if group_index == len(groups) - 1:
                end = cue.end
            else:
                end = cue.start + cue_duration * consumed_weight / total_weight
            segments.append(CaptionSegment(cursor, end, group))
            cursor = end
    return segments


def write_srt(
    cues: list[CaptionCue],
    path: str | Path,
    *,
    uppercase: bool = DEFAULT_CAPTION_UPPERCASE,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for index, segment in enumerate(caption_segments(cues), start=1):
        if segment.end <= segment.start:
            continue
        blocks.append(
            f"{index}\n{srt_timestamp(segment.start)} --> {srt_timestamp(segment.end)}\n"
            f"{wrap_caption(segment.text.upper() if uppercase else segment.text, max_chars=24)}"
        )
    target.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")
    return target


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", r"\N")


def _karaoke_text(segment: CaptionSegment, *, uppercase: bool = DEFAULT_CAPTION_UPPERCASE) -> str:
    if segment.word_timings:
        parts: list[str] = []
        previous_end: float | None = None
        for word in segment.word_timings:
            if previous_end is not None:
                gap = max(0, round((word.start - previous_end) * 100))
                parts.append(f"{{\\kf{gap}}} " if gap else " ")
            text = word.text.upper() if uppercase else word.text
            parts.append(f"{{\\kf{max(1, round((word.end - word.start) * 100))}}}{_ass_escape(text)}")
            previous_end = word.end
        return "".join(parts)
    total_weight = sum(_word_weight(word) for word in segment.words)
    total_centiseconds = max(1, round((segment.end - segment.start) * 100))
    durations: list[int] = []
    consumed = 0
    for index, word in enumerate(segment.words):
        if index == len(segment.words) - 1:
            duration = max(1, total_centiseconds - consumed)
        else:
            duration = max(1, round(total_centiseconds * _word_weight(word) / total_weight))
        durations.append(duration)
        consumed += duration
    return " ".join(
        f"{{\\kf{duration}}}{_ass_escape(word.upper() if uppercase else word)}"
        for word, duration in zip(segment.words, durations)
    )


def _entrance_effect_tags(effect: str | None) -> str:
    if effect == "pop":
        return r"\fscx72\fscy72\alpha&HFF&\t(0,120,\fscx100\fscy100\alpha&H00&)"
    return ""


def write_ass(
    cues: list[CaptionCue],
    path: str | Path,
    *,
    font_name: str = DEFAULT_CAPTION_FONT,
    font_size: int = DEFAULT_CAPTION_FONT_SIZE,
    font_weight: int = DEFAULT_CAPTION_FONT_WEIGHT,
    margin_vertical: int = 250,
    vertical_position_percent: float | None = None,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    uppercase: bool = DEFAULT_CAPTION_UPPERCASE,
    entrance_effect: str | None = DEFAULT_CAPTION_ENTRANCE_EFFECT,
) -> Path:
    """Write bold short-form ASS captions with word-by-word color progress."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    positioned = vertical_position_percent is not None
    position_y = round(
        play_res_y * (1 - min(100.0, max(0.0, float(vertical_position_percent or 0))) / 100)
    )
    alignment = 5 if positioned else 2
    style_margin = 0 if positioned else margin_vertical
    event_overrides = f"\\b{max(100, min(900, int(font_weight)))}{_entrance_effect_tags(entrance_effect)}"
    if positioned:
        event_overrides += f"\\an5\\pos({play_res_x // 2},{position_y})"
    style_override = f"{{{event_overrides}}}"
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Caption,{font_name},{font_size},&H00FFFFFF,&H0000D7FF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,4,1,{alignment},90,90,{style_margin},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,Effect,Text
"""
    events = []
    for segment in caption_segments(cues):
        events.append(
            f"Dialogue: 0,{_ass_timestamp(segment.start)},{_ass_timestamp(segment.end)},"
            f"Caption,,0,0,0,{style_override}{_karaoke_text(segment, uppercase=uppercase)}"
        )
    target.write_text(header + "\n".join(events) + ("\n" if events else ""), encoding="utf-8-sig")
    return target

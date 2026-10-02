from __future__ import annotations

import gc
from dataclasses import dataclass
import difflib
import os
from pathlib import Path
import re
from typing import Any, Iterable

import torch

from app.captions import CaptionCue, CaptionWord
from app.schemas import normalized_words, phrase_word_span


@dataclass(frozen=True)
class WhisperTranscript:
    cues: tuple[CaptionCue, ...]
    observed_words: tuple[CaptionWord, ...]


def _word_from_whisper(word: Any) -> CaptionWord | None:
    text = str(getattr(word, "word", "")).strip()
    start = getattr(word, "start", None)
    end = getattr(word, "end", None)
    if not text or start is None or end is None:
        return None
    start_value = max(0.0, float(start))
    end_value = max(start_value, float(end))
    if end_value <= start_value:
        return None
    return CaptionWord(text=text, start=start_value, end=end_value)


def caption_cues_from_segments(segments: Iterable[Any]) -> list[CaptionCue]:
    """Convert faster-whisper segments with word timestamps to caption cues."""
    cues: list[CaptionCue] = []
    for segment in segments:
        words = tuple(
            word
            for raw_word in (getattr(segment, "words", None) or ())
            if (word := _word_from_whisper(raw_word)) is not None
        )
        if words:
            cues.append(CaptionCue(words[0].start, words[-1].end, " ".join(word.text for word in words), words))
            continue
        text = str(getattr(segment, "text", "")).strip()
        start = getattr(segment, "start", None)
        end = getattr(segment, "end", None)
        if text and start is not None and end is not None and float(end) > float(start):
            cues.append(CaptionCue(max(0.0, float(start)), float(end), text))
    return cues


def observed_words_from_segments(segments: Iterable[Any]) -> tuple[CaptionWord, ...]:
    words = [
        word
        for segment in segments
        for raw_word in (getattr(segment, "words", None) or ())
        if (word := _word_from_whisper(raw_word)) is not None
    ]
    words.sort(key=lambda word: (word.start, word.end))
    return tuple(words)


def _normalize_word(word: str) -> str:
    return re.sub(r"[^\wÀ-ÿ]", "", word.casefold())


def _expected_words_with_whisper_timing(
    text: str,
    start: float,
    end: float,
    observed: tuple[CaptionWord, ...],
) -> tuple[CaptionWord, ...]:
    """Keep the script text while borrowing real word intervals from Whisper."""
    expected = tuple(re.findall(r"\S+", text.strip()))
    if not expected or not observed:
        return ()

    expected_keys = tuple(_normalize_word(word) for word in expected)
    observed_keys = tuple(_normalize_word(word.text) for word in observed)
    anchors: dict[int, CaptionWord] = {}
    matcher = difflib.SequenceMatcher(a=expected_keys, b=observed_keys, autojunk=False)
    for tag, expected_start, expected_end, observed_start, observed_end in matcher.get_opcodes():
        if tag in {"equal", "replace"}:
            for expected_index, observed_index in zip(
                range(expected_start, expected_end), range(observed_start, observed_end)
            ):
                anchors[expected_index] = observed[observed_index]

    result: list[CaptionWord | None] = [None] * len(expected)
    for index, word in anchors.items():
        result[index] = CaptionWord(expected[index], word.start, word.end)

    anchor_indices = sorted(anchors)
    for index, value in enumerate(result):
        if value is not None:
            continue
        previous = max((item for item in anchor_indices if item < index), default=None)
        following = min((item for item in anchor_indices if item > index), default=None)
        left = result[previous].end if previous is not None and result[previous] else start
        right = result[following].start if following is not None and result[following] else end
        gap_indices = [
            item
            for item in range(len(result))
            if result[item] is None
            and (previous is None or item > previous)
            and (following is None or item < following)
        ]
        position = gap_indices.index(index)
        gap_size = max(0.01, right - left)
        slot = gap_size / max(1, len(gap_indices))
        word_start = left + slot * position
        word_end = right if position == len(gap_indices) - 1 else left + slot * (position + 1)
        result[index] = CaptionWord(expected[index], max(start, word_start), min(end, word_end))
    return tuple(word for word in result if word is not None)


def align_caption_cues(
    expected_cues: Iterable[CaptionCue],
    segments: Iterable[Any],
) -> list[CaptionCue]:
    """Apply Whisper's word intervals to the original script cues."""
    observed: list[CaptionWord] = []
    for segment in segments:
        observed.extend(
            word
            for raw_word in (getattr(segment, "words", None) or ())
            if (word := _word_from_whisper(raw_word)) is not None
        )
    observed.sort(key=lambda word: (word.start, word.end))

    aligned: list[CaptionCue] = []
    for cue in expected_cues:
        words = tuple(word for word in observed if word.end > cue.start and word.start < cue.end)
        timed_words = _expected_words_with_whisper_timing(cue.text, cue.start, cue.end, words)
        aligned.append(CaptionCue(cue.start, cue.end, cue.text, timed_words))
    return aligned


def anchor_start_time(
    narration: str,
    start_phrase: str,
    observed_words: Iterable[CaptionWord],
    *,
    scene_start: float,
    scene_end: float,
    scene_id: str,
    shot_index: int,
) -> float:
    """Locate an anchor using only lexically observed Whisper words."""
    try:
        anchor_start, anchor_end = phrase_word_span(narration, start_phrase)
    except ValueError as exc:
        raise ValueError(
            f"Cena {scene_id}, plano {shot_index + 1}, frase {start_phrase!r}: {exc}"
        ) from exc

    expected = normalized_words(narration)
    observed = tuple(
        word
        for word in observed_words
        if word.end > scene_start and word.start < scene_end
    )
    observed_keys = tuple(_normalize_word(word.text) for word in observed)
    mapping: dict[int, int] = {}
    matcher = difflib.SequenceMatcher(a=expected, b=observed_keys, autojunk=False)
    for tag, expected_start, expected_end, observed_start, _observed_end in matcher.get_opcodes():
        if tag != "equal":
            continue
        for offset in range(expected_end - expected_start):
            mapping[expected_start + offset] = observed_start + offset

    expected_indices = list(range(anchor_start, anchor_end))
    if any(index not in mapping for index in expected_indices):
        raise ValueError(
            f"Cena {scene_id}, plano {shot_index + 1}, frase {start_phrase!r}: "
            "o Whisper nao reconheceu lexicalmente toda a frase ancora; ajuste o roteiro ou a frase"
        )
    observed_indices = [mapping[index] for index in expected_indices]
    expected_observed_indices = list(range(observed_indices[0], observed_indices[0] + len(observed_indices)))
    if observed_indices != expected_observed_indices:
        raise ValueError(
            f"Cena {scene_id}, plano {shot_index + 1}, frase {start_phrase!r}: "
            "as palavras reconhecidas da ancora nao formam uma sequencia temporal coerente"
        )
    matched = tuple(observed[index] for index in observed_indices)
    if any(right.start <= left.start or right.end <= left.start for left, right in zip(matched, matched[1:])):
        raise ValueError(
            f"Cena {scene_id}, plano {shot_index + 1}, frase {start_phrase!r}: "
            "os timestamps reconhecidos nao sao crescentes"
        )
    start_time = matched[0].start
    if not scene_start <= start_time < scene_end:
        raise ValueError(
            f"Cena {scene_id}, plano {shot_index + 1}, frase {start_phrase!r}: "
            "o timestamp reconhecido ficou fora dos limites da cena"
        )
    return start_time


class WhisperAligner:
    """Lazy local Whisper transcription for word-accurate captions."""

    def __init__(self, model_name: str | None = None, device: str | None = None, compute_type: str | None = None):
        self.model_name = model_name or os.getenv("WHISPER_MODEL", "small")
        self.device = device or os.getenv("WHISPER_DEVICE", "cuda")
        self.compute_type = compute_type or os.getenv("WHISPER_COMPUTE_TYPE", "float16")
        self.cache_dir = Path(os.getenv("WHISPER_CACHE_DIR", "/root/.cache/huggingface/whisper"))
        self.model = None

    def _get_model(self):
        if self.model is not None:
            return self.model
        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("Whisper foi configurado para CUDA, mas CUDA nao esta disponivel no container.")
        try:
            from faster_whisper import WhisperModel

            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                download_root=str(self.cache_dir),
            )
            return self.model
        except Exception as exc:
            raise RuntimeError(
                "Nao foi possivel carregar o Whisper local. Mantenha a rede disponivel na primeira execucao "
                "para baixar o modelo e confira a compatibilidade CUDA."
            ) from exc

    def transcribe(
        self,
        audio_path: str | Path,
        expected_cues: Iterable[CaptionCue] | None = None,
    ) -> list[CaptionCue]:
        return list(self.transcribe_with_words(audio_path, expected_cues=expected_cues).cues)

    def transcribe_with_words(
        self,
        audio_path: str | Path,
        expected_cues: Iterable[CaptionCue] | None = None,
    ) -> WhisperTranscript:
        path = Path(audio_path)
        if not path.is_file():
            raise FileNotFoundError(f"Audio para sincronizacao nao encontrado: {path}")
        try:
            segments, _info = self._get_model().transcribe(
                str(path),
                language="pt",
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            segments = list(segments)
            observed_words = observed_words_from_segments(segments)
            cues = (
                align_caption_cues(expected_cues, segments)
                if expected_cues is not None
                else caption_cues_from_segments(segments)
            )
        except Exception as exc:
            raise RuntimeError(f"Whisper falhou ao sincronizar as legendas: {exc}") from exc
        if not cues:
            raise RuntimeError("Whisper nao encontrou fala no audio para criar as legendas.")
        if not observed_words:
            raise RuntimeError("Whisper nao retornou timestamps de palavras para sincronizar o audio.")
        return WhisperTranscript(tuple(cues), observed_words)

    def release(self) -> None:
        self.model = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()

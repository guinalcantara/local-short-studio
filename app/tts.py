from __future__ import annotations

import os
from pathlib import Path
import re

import numpy as np
import soundfile as sf
import torch


SAMPLE_RATE = 24000


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?…])\s+", text) if part.strip()]


class KokoroTTS:
    def __init__(self, device: str | None = None, voice: str | None = None):
        self.device = device or os.getenv("TTS_DEVICE", "cuda")
        self.voice = voice or os.getenv("TTS_VOICE", "pf_dora")
        self.speed = float(os.getenv("TTS_SPEED", "1.0"))
        self.pipeline = None

    def _get_pipeline(self):
        if self.pipeline is None:
            if self.device == "cuda" and not torch.cuda.is_available():
                raise RuntimeError("TTS_DEVICE=cuda, mas torch.cuda.is_available() retornou falso. Confira Docker/WSL/CUDA.")
            from kokoro import KPipeline

            self.pipeline = KPipeline(lang_code="p", device=self.device)
        return self.pipeline

    def generate_sentence(self, text: str, voice: str | None = None, speed: float | None = None) -> np.ndarray:
        pipeline = self._get_pipeline()
        chunks = []
        for _, _, audio in pipeline(text, voice=voice or self.voice, speed=speed or self.speed, split_pattern=r"\n+"):
            if audio is not None:
                chunks.append(np.asarray(audio.detach().cpu(), dtype=np.float32).reshape(-1))
        if not chunks:
            raise RuntimeError("Kokoro não produziu áudio para esta frase.")
        return np.concatenate(chunks)

    def write_sentence(self, text: str, path: str | Path, voice: str | None = None, speed: float | None = None) -> float:
        audio = self.generate_sentence(text, voice=voice, speed=speed)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        sf.write(target, audio, SAMPLE_RATE, subtype="PCM_16")
        return len(audio) / SAMPLE_RATE

    def release(self) -> None:
        self.pipeline = None
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()


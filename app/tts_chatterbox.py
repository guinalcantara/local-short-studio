from __future__ import annotations

import gc
import inspect
import os
from pathlib import Path

import numpy as np
import torch

from app.tts import SAMPLE_RATE


PTBR_REPO_ID = "ResembleAI/Chatterbox-Multilingual-pt-br"
BASE_REPO_ID = "ResembleAI/chatterbox"


class ChatterboxPTBRTTS:
    """Lazy local loader for the official Chatterbox Brazilian Portuguese pack."""

    def __init__(
        self,
        device: str | None = None,
        exaggeration: float | None = None,
        cfg_weight: float | None = None,
        temperature: float | None = None,
        reference_audio_path: str | Path | None = None,
    ):
        self.device = device or os.getenv("CHATTERBOX_DEVICE", "cuda")
        self.exaggeration = float(exaggeration if exaggeration is not None else os.getenv("CHATTERBOX_EXAGGERATION", "0.5"))
        self.cfg_weight = float(cfg_weight if cfg_weight is not None else os.getenv("CHATTERBOX_CFG_WEIGHT", "0.5"))
        self.temperature = float(temperature if temperature is not None else os.getenv("CHATTERBOX_TEMPERATURE", "0.8"))
        self.reference_audio_path = Path(reference_audio_path) if reference_audio_path else None
        self._reference_loaded_path: str | None = None
        self.model = None

    def set_reference_audio(self, reference_audio_path: str | Path | None) -> None:
        self.reference_audio_path = Path(reference_audio_path) if reference_audio_path else None
        self._reference_loaded_path = None

    @staticmethod
    def _link(target: Path, source: Path) -> None:
        if not source.exists():
            raise FileNotFoundError(f"Chatterbox weight not found: {source}")
        if target.is_symlink() or target.exists():
            if target.is_symlink() and target.resolve() == source.resolve():
                return
            target.unlink()
        target.symlink_to(source)

    def _prepare_ptbr_checkpoint(self, base_dir: Path, ptbr_dir: Path) -> Path:
        cache_dir = Path(
            os.getenv(
                "CHATTERBOX_CACHE_DIR",
                "/root/.cache/huggingface/local-short-studio/chatterbox-ptbr",
            )
        )
        cache_dir.mkdir(parents=True, exist_ok=True)
        mapping = {
            "ve.pt": base_dir / "ve.pt",
            "conds.pt": base_dir / "conds.pt",
            # The official PT-BR single-language pack pairs this V3 decoder
            # with t3_pt_br.safetensors. The upstream loader expects the
            # generic filename s3gen.pt.
            "s3gen.pt": base_dir / "s3gen_v3.pt",
            "grapheme_mtl_merged_expanded_v1.json": base_dir / "grapheme_mtl_merged_expanded_v1.json",
            "t3_pt_br.safetensors": ptbr_dir / "t3_pt_br.safetensors",
        }
        for target_name, source in mapping.items():
            self._link(cache_dir / target_name, source)
        return cache_dir

    def _get_model(self):
        if self.model is not None:
            return self.model
        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError(
                "Chatterbox PT-BR foi selecionado, mas CUDA nao esta disponivel. "
                "Confira o driver NVIDIA, WSL 2 e o Docker Desktop."
            )
        try:
            from huggingface_hub import snapshot_download
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS, S3Gen

            base_dir = Path(
                snapshot_download(
                    repo_id=os.getenv("CHATTERBOX_BASE_REPO", BASE_REPO_ID),
                    allow_patterns=[
                        "ve.pt",
                        "conds.pt",
                        "s3gen_v3.pt",
                        "grapheme_mtl_merged_expanded_v1.json",
                    ],
                    token=os.getenv("HF_TOKEN"),
                )
            )
            ptbr_dir = Path(
                snapshot_download(
                    repo_id=os.getenv("CHATTERBOX_PTBR_REPO", PTBR_REPO_ID),
                    allow_patterns=["t3_pt_br.safetensors"],
                    token=os.getenv("HF_TOKEN"),
                )
            )
            checkpoint_dir = self._prepare_ptbr_checkpoint(base_dir, ptbr_dir)
            from_local = ChatterboxMultilingualTTS.from_local
            if "t3_model" not in inspect.signature(from_local).parameters:
                raise RuntimeError(
                    "O pacote Chatterbox instalado nao possui a API V3 t3_model. "
                    "Reconstrua a imagem Docker para instalar o commit oficial fixado."
                )
            original_load_state_dict = S3Gen.load_state_dict

            def load_v3_state_dict(instance, state_dict, *args, **kwargs):
                # V3 omits mel-filter buffers that are recreated by S3Gen.__init__.
                kwargs.setdefault("strict", False)
                result = original_load_state_dict(instance, state_dict, *args, **kwargs)
                allowed_missing = {"tokenizer._mel_filters", "tokenizer.window"}
                unexpected = set(result.unexpected_keys)
                missing = set(result.missing_keys) - allowed_missing
                if missing or unexpected:
                    raise RuntimeError(
                        f"Incompatibilidade de pesos Chatterbox: ausentes={sorted(missing)}, "
                        f"inesperados={sorted(unexpected)}"
                    )
                return result

            S3Gen.load_state_dict = load_v3_state_dict
            try:
                self.model = from_local(
                    checkpoint_dir,
                    device=self.device,
                    t3_model="t3_pt_br.safetensors",
                )
            finally:
                S3Gen.load_state_dict = original_load_state_dict
            return self.model
        except Exception as exc:
            raise RuntimeError(
                "Nao foi possivel carregar o Chatterbox PT-BR. "
                "Na primeira execucao, mantenha a rede disponivel para baixar os pesos; "
                "depois verifique o cache em models/kokoro e a compatibilidade CUDA."
            ) from exc

    def _prepare_reference(self, model) -> None:
        if self.reference_audio_path is None:
            return
        reference_path = self.reference_audio_path
        if not reference_path.is_file():
            raise FileNotFoundError(f"Audio de referencia nao encontrado: {reference_path}")
        resolved_path = str(reference_path.resolve())
        if self._reference_loaded_path == resolved_path:
            return
        try:
            # Prepare the speaker/emotion conditionals once per generation.
            # Calling generate(audio_prompt_path=...) for every sentence would
            # recompute the voice embedding and make long Shorts unnecessarily slow.
            model.prepare_conditionals(str(reference_path), exaggeration=self.exaggeration)
        except Exception as exc:
            raise RuntimeError(
                "Nao foi possivel preparar o audio de referencia. "
                "Use um clipe curto, limpo, sem musica ou reverberacao."
            ) from exc
        self._reference_loaded_path = resolved_path

    def generate_block(self, text: str, voice: str | None = None, speed: float | None = None) -> np.ndarray:
        del voice, speed
        model = self._get_model()
        try:
            self._prepare_reference(model)
            audio = model.generate(
                text,
                language_id="pt",
                exaggeration=self.exaggeration,
                cfg_weight=self.cfg_weight,
                temperature=self.temperature,
            )
        except Exception as exc:
            raise RuntimeError(f"Chatterbox falhou ao gerar a frase: {exc}") from exc
        array = audio.detach().float().cpu().numpy() if torch.is_tensor(audio) else np.asarray(audio, dtype=np.float32)
        array = np.asarray(array, dtype=np.float32).reshape(-1)
        sample_rate = int(getattr(model, "sr", SAMPLE_RATE))
        if sample_rate != SAMPLE_RATE and len(array):
            source_positions = np.linspace(0.0, 1.0, num=len(array), endpoint=False)
            target_length = round(len(array) * SAMPLE_RATE / sample_rate)
            target_positions = np.linspace(0.0, 1.0, num=target_length, endpoint=False)
            array = np.interp(target_positions, source_positions, array).astype(np.float32)
        if not len(array):
            raise RuntimeError("Chatterbox nao produziu audio para esta frase.")
        return array

    def generate_sentence(self, text: str, voice: str | None = None, speed: float | None = None) -> np.ndarray:
        """Compatibility alias for callers that synthesize one sentence."""
        return self.generate_block(text, voice=voice, speed=speed)

    def release(self) -> None:
        self.model = None
        self._reference_loaded_path = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()

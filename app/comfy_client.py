from __future__ import annotations

import copy
import json
import os
import random
import time
from pathlib import Path
from typing import Any

import requests


class ComfyClient:
    def __init__(self, base_url: str | None = None, workflow_path: str | None = None):
        self.base_url = (base_url or os.getenv("COMFYUI_URL", "http://comfyui:8188")).rstrip("/")
        self.workflow_path = Path(workflow_path or os.getenv("COMFYUI_WORKFLOW", "/workspace/workflows/sd15_portrait_api.json"))
        self.timeout = 20

    def health(self) -> tuple[bool, str]:
        try:
            response = requests.get(f"{self.base_url}/system_stats", timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            devices = data.get("devices", [])
            if not devices:
                return True, "ComfyUI respondeu; não informou dispositivos CUDA."
            names = ", ".join(device.get("name", "GPU") for device in devices)
            return True, f"ComfyUI pronto: {names}"
        except Exception as exc:
            return False, f"ComfyUI não respondeu em {self.base_url}: {exc}"

    def generate_image(
        self,
        prompt_text: str,
        output_path: str | Path,
        *,
        checkpoint: str,
        width: int,
        height: int,
        steps: int,
        cfg: float,
        seed: int | None = None,
        timeout_seconds: int = 900,
    ) -> Path:
        if not self.workflow_path.exists():
            raise FileNotFoundError(f"Workflow do ComfyUI não encontrado: {self.workflow_path}")
        workflow: dict[str, Any] = json.loads(self.workflow_path.read_text(encoding="utf-8"))
        actual_seed = int(seed if seed is not None else random.randint(1, 2**31 - 1))
        workflow["1"]["inputs"]["ckpt_name"] = checkpoint
        workflow["2"]["inputs"]["text"] = prompt_text
        workflow["4"]["inputs"].update({"width": width, "height": height})
        workflow["5"]["inputs"].update({"seed": actual_seed, "steps": steps, "cfg": cfg})
        workflow["7"]["inputs"]["filename_prefix"] = f"local_short_studio/scene_{actual_seed}"

        submitted = requests.post(f"{self.base_url}/prompt", json={"prompt": workflow}, timeout=self.timeout)
        submitted.raise_for_status()
        prompt_id = submitted.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI não retornou prompt_id: {submitted.text[:500]}")

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            history_response = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=self.timeout)
            history_response.raise_for_status()
            history = history_response.json().get(prompt_id)
            if history:
                status = history.get("status", {})
                messages = status.get("messages", [])
                if any("execution_error" in str(message) for message in messages):
                    raise RuntimeError(f"ComfyUI falhou ao gerar a imagem: {messages[-1] if messages else status}")
                outputs = history.get("outputs", {})
                images = [item for node in outputs.values() for item in node.get("images", [])]
                if images:
                    image_meta = images[0]
                    image_response = requests.get(
                        f"{self.base_url}/view",
                        params={
                            "filename": image_meta["filename"],
                            "subfolder": image_meta.get("subfolder", ""),
                            "type": image_meta.get("type", "output"),
                        },
                        timeout=60,
                    )
                    image_response.raise_for_status()
                    target = Path(output_path)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(image_response.content)
                    return target
            time.sleep(2)
        raise TimeoutError(f"ComfyUI excedeu {timeout_seconds}s ao gerar a cena.")

    def free_memory(self) -> None:
        response = requests.post(
            f"{self.base_url}/api/free",
            json={"unload_models": True, "free_memory": True},
            timeout=30,
        )
        response.raise_for_status()


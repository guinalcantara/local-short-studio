from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
import torch

from app.comfy_client import ComfyClient
from app.pipeline import ShortPipeline
from app.schemas import VideoProject, example_project


st.set_page_config(page_title="Local Short Studio", page_icon="🎬", layout="wide")
st.title("Local Short Studio")
st.write("Transforme um roteiro por cenas em imagens, narração e um Short vertical — tudo localmente.")
st.caption("A inferência de imagem e voz usa CUDA. FFmpeg aplica os movimentos suaves, as transições e exporta o MP4.")

with st.container(border=True):
    cuda_ok = torch.cuda.is_available()
    col1, col2 = st.columns(2)
    col1.metric("CUDA", "Disponível" if cuda_ok else "Não detectada")
    if cuda_ok:
        props = torch.cuda.get_device_properties(0)
        col2.metric("GPU detectada", f"{props.name} · {props.total_memory / (1024**3):.1f} GB")
    else:
        col2.metric("GPU detectada", "Verifique Docker Desktop + WSL 2")
    comfy_ok, comfy_status = ComfyClient().health()
    st.write(("✅ " if comfy_ok else "⚠️ ") + comfy_status)

sample_project = example_project()
sample_text = sample_project.to_json()
uploaded = st.file_uploader("Importe um projeto de cenas (.json)", type=["json"])
if uploaded:
    try:
        project_text = uploaded.getvalue().decode("utf-8")
    except UnicodeDecodeError:
        st.error("O JSON precisa estar codificado em UTF-8.")
        project_text = sample_text
else:
    project_text = sample_text

st.download_button(
    "Baixar modelo de projeto",
    data=sample_text,
    file_name="modelo_projeto_short.json",
    mime="application/json",
)

with st.expander("Editar roteiro e cenas", expanded=True):
    project_text = st.text_area(
        "JSON do projeto",
        value=project_text,
        height=430,
        help="Cada cena precisa de narration e image_prompt. O campo visual_style mantém uma aparência consistente entre as imagens.",
    )

parsed = None
try:
    parsed = VideoProject.from_json_text(project_text)
except Exception as exc:
    st.error(f"Projeto inválido: {exc}")

left, right = st.columns(2)
captions_enabled = left.checkbox(
    "Adicionar legendas modernas",
    value=bool(parsed.captions.enabled) if parsed else False,
    help="Desmarcado: não queima texto no vídeo nem cria arquivo SRT.",
)
voice = right.text_input("Voz Kokoro", value=parsed.voice if parsed else "pf_dora", help="Código padrão pt-BR: pf_dora")
speech_speed = st.slider(
    "Velocidade da narração",
    min_value=0.75,
    max_value=1.25,
    value=float(parsed.speech_speed) if parsed else 1.0,
    step=0.05,
)

music_upload = st.file_uploader("Música de fundo opcional (com direitos de uso)", type=["mp3", "wav", "m4a", "aac"])

if st.button("Gerar Short", type="primary", disabled=parsed is None, use_container_width=True):
    project = VideoProject.from_json_text(project_text)
    project.captions.enabled = captions_enabled
    project.voice = voice.strip() or "pf_dora"
    project.speech_speed = speech_speed
    if music_upload is not None:
        music_dir = Path(os.getenv("INPUT_DIR", "/workspace/input")) / "music"
        music_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(music_upload.name).suffix.lower() or ".mp3"
        music_path = music_dir / f"background{suffix}"
        music_path.write_bytes(music_upload.getvalue())
        project.music_path = str(music_path)

    progress_bar = st.progress(0.0, text="Preparando geração…")
    status_text = st.empty()

    def update_progress(message: str, fraction: float | None = None):
        status_text.info(message)
        if fraction is not None:
            progress_bar.progress(min(1.0, max(0.0, fraction)), text=message)

    try:
        with st.spinner("Gerando imagens e voz localmente; o tempo depende do número de cenas."):
            output_video = ShortPipeline(progress=update_progress).run(project)
        status_text.success("Short finalizado.")
        progress_bar.progress(1.0, text="Pronto")
        st.video(str(output_video))
        st.download_button(
            "Baixar MP4",
            data=output_video.read_bytes(),
            file_name=output_video.name,
            mime="video/mp4",
            type="primary",
        )
        project_dir = output_video.parent
        st.write(f"Arquivos salvos em: `{project_dir}`")
        if captions_enabled:
            srt_path = output_video.with_suffix(".srt")
            if srt_path.exists():
                st.download_button("Baixar legendas SRT", data=srt_path.read_bytes(), file_name=srt_path.name, mime="application/x-subrip")
    except Exception as exc:
        status_text.error("A geração parou. Veja a etapa indicada na mensagem abaixo.")
        st.exception(exc)

st.divider()
st.markdown("**Fluxo local:** roteiro JSON → ComfyUI/SD 1.5 → libera VRAM → Kokoro pt-BR em CUDA → FFmpeg → MP4 9:16")

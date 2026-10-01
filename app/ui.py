from __future__ import annotations

import os
from pathlib import Path
import time

import streamlit as st
import torch

from app.image_archive import ImageZipError, ImageZipValidation, validate_image_zip
from app.pipeline import ShortPipeline
from app.schemas import VideoProject, example_project
from app.voices import KOKORO_VOICES, TTS_ENGINES, normalize_voice, tts_engine_label, voice_label


VIDEO_PREVIEW_WIDTH = 360


st.set_page_config(page_title="Local Short Studio", page_icon="🎬", layout="wide")
st.title("Local Short Studio")
st.write("Transforme um roteiro e um ZIP de imagens em narração e um Short vertical local.")
st.caption("As imagens são preparadas previamente e enviadas com o roteiro; Kokoro usa CUDA para a voz e FFmpeg monta o MP4.")

with st.container(border=True):
    cuda_ok = torch.cuda.is_available()
    col1, col2 = st.columns(2)
    col1.metric("CUDA para Kokoro", "Disponível" if cuda_ok else "Não detectada")
    if cuda_ok:
        props = torch.cuda.get_device_properties(0)
        col2.metric("GPU detectada", f"{props.name} · {props.total_memory / (1024**3):.1f} GB")
    else:
        col2.metric("GPU detectada", "Verifique Docker Desktop + WSL 2")

sample_project = example_project()
sample_text = sample_project.to_json()
uploaded = st.file_uploader("1. Importe o projeto de cenas (.json)", type=["json"])
project_uploaded = uploaded is not None
if uploaded:
    try:
        project_text = uploaded.getvalue().decode("utf-8")
    except UnicodeDecodeError:
        st.error("O JSON precisa estar codificado em UTF-8.")
        project_text = ""
else:
    project_text = sample_text
    st.info("Envie o modelo JSON para habilitar a geração.")

st.download_button(
    "Baixar modelo de projeto",
    data=sample_text,
    file_name="modelo_projeto_short.json",
    mime="application/json",
)

with st.expander("Revisar roteiro e metadados", expanded=True):
    project_text = st.text_area(
        "JSON do projeto",
        value=project_text,
        height=430,
        help="Cada cena precisa de narration e image_path. image_path deve ser o nome do arquivo presente no ZIP.",
    )

parsed: VideoProject | None = None
try:
    if project_text.strip():
        parsed = VideoProject.from_json_text(project_text)
except Exception as exc:
    st.error(f"Projeto inválido: {exc}")

images_upload = st.file_uploader(
    "2. Importe as imagens das cenas (.zip)",
    type=["zip"],
    help="O ZIP pode conter imagens na raiz ou em uma única subpasta. Use PNG, JPG, JPEG ou WebP.",
)

engine_codes = [code for _, code in TTS_ENGINES]
tts_engine = st.selectbox(
    "Mecanismo de narração",
    options=engine_codes,
    format_func=tts_engine_label,
    help="Escolha o mecanismo usado nesta geração. A escolha não altera o JSON do projeto.",
)

left, right = st.columns(2)
captions_enabled = left.checkbox(
    "Adicionar legendas modernas",
    value=bool(parsed.captions.enabled) if parsed else False,
    help="Desmarcado: não queima texto no vídeo nem cria arquivo SRT.",
)
if tts_engine == "kokoro":
    voice_codes = [code for _, code in KOKORO_VOICES]
    selected_voice = normalize_voice(parsed.voice if parsed else None)
    voice = right.selectbox(
        "Voz da narração",
        options=voice_codes,
        index=voice_codes.index(selected_voice),
        format_func=voice_label,
        help="Todas as falas usam a voz escolhida em português brasileiro.",
    )
    speech_speed = st.slider(
        "Velocidade da narração",
        min_value=0.75,
        max_value=1.25,
        value=float(parsed.speech_speed) if parsed else 1.0,
        step=0.05,
    )
    chatterbox_settings = None
else:
    voice = normalize_voice(parsed.voice if parsed else None)
    speech_speed = float(parsed.speech_speed) if parsed else 1.0
    st.info("Chatterbox usa o checkpoint dedicado pt-BR e uma voz interna; os controles abaixo são os compatíveis com esse mecanismo.")
    cb_left, cb_middle, cb_right = st.columns(3)
    chatterbox_exaggeration = cb_left.slider("Expressividade", 0.25, 1.0, 0.5, 0.05)
    chatterbox_cfg = cb_middle.slider("Controle de ritmo", 0.2, 0.8, 0.5, 0.05)
    chatterbox_temperature = cb_right.slider("Variação", 0.3, 1.2, 0.8, 0.05)
    chatterbox_settings = {
        "exaggeration": chatterbox_exaggeration,
        "cfg_weight": chatterbox_cfg,
        "temperature": chatterbox_temperature,
    }

music_upload = st.file_uploader("Música de fundo opcional (com direitos de uso)", type=["mp3", "wav", "m4a", "aac"])

zip_validation: ImageZipValidation | None = None
if images_upload is None:
    st.info("Envie o ZIP de imagens para validar o mapeamento das cenas.")
elif parsed is not None:
    try:
        zip_validation = validate_image_zip(images_upload.getvalue(), [scene.image_path for scene in parsed.scenes])
        st.success(f"ZIP válido: {zip_validation.image_count} imagens encontradas para {len(parsed.scenes)} cenas.")
        st.caption("Arquivos encontrados: " + ", ".join(zip_validation.found_names))
        for warning in zip_validation.warnings:
            st.warning(warning)
    except ImageZipError as exc:
        st.error(f"ZIP de imagens inválido: {exc}")

can_generate = project_uploaded and parsed is not None and images_upload is not None and zip_validation is not None
if st.button("Gerar Short", type="primary", disabled=not can_generate, use_container_width=True):
    project = VideoProject.from_json_text(project_text)
    project.captions.enabled = captions_enabled
    if tts_engine == "kokoro":
        project.voice = voice
        project.speech_speed = speech_speed
    if music_upload is not None:
        music_dir = Path(os.getenv("INPUT_DIR", "/workspace/input")) / "music"
        music_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(music_upload.name).suffix.lower() or ".mp3"
        music_path = music_dir / f"background{suffix}"
        music_path.write_bytes(music_upload.getvalue())
        project.music_path = str(music_path)

    progress_bar = st.progress(0.0, text="Preparando validação…")
    status_text = st.empty()
    progress_started = time.perf_counter()

    def update_progress(message: str, fraction: float | None = None):
        elapsed = time.perf_counter() - progress_started
        status_text.info(f"{message}  ·  decorrido: {elapsed:.0f}s")
        if fraction is not None:
            progress_bar.progress(min(1.0, max(0.0, fraction)), text=message)

    try:
        with st.spinner("Gerando o Short…"):
            output_video = ShortPipeline(
                progress=update_progress,
                tts_engine=tts_engine,
                chatterbox_settings=chatterbox_settings,
            ).run(project, images_upload.getvalue())
        status_text.success("Short finalizado.")
        progress_bar.progress(1.0, text="Pronto")
        st.video(str(output_video), width=VIDEO_PREVIEW_WIDTH)
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
st.markdown("**Fluxo local:** modelo JSON + ZIP → validação → Kokoro pt-BR em CUDA → FFmpeg → MP4 9:16")

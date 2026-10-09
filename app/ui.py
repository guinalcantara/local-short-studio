from __future__ import annotations

import os
from pathlib import Path
import time
from io import BytesIO

import streamlit as st
import torch
from PIL import Image, ImageOps

from app.captions import DEFAULT_CAPTION_FONT_SIZE, DEFAULT_CAPTION_HEIGHT_PERCENT
from app.image_archive import ImageZipError, ImageZipValidation, validate_image_zip
from app.incremental import WorkspacePipeline
from app.music_catalog import MusicCatalog, MusicCatalogError, load_music_catalog
from app.pipeline import ShortPipeline, project_image_paths
from app.performance_ui import render_channel_performance
from app.renderer import camera_crop_rect
from app.schemas import Camera, VideoProject, example_project
from app.voices import KOKORO_VOICES, TTS_ENGINES, normalize_voice, tts_engine_label, voice_label
from app.workspace import ProjectWorkspace, WorkspaceError, file_sha256
from app.youtube import (
    YouTubeAlreadyPublishedError,
    YouTubeError,
    cancel_youtube_authorization,
    is_oauth_configured,
    list_youtube_accounts,
    load_youtube_publication,
    pending_youtube_authorization,
    publish_to_youtube,
    remove_youtube_account,
    start_youtube_authorization,
    youtube_authorization_status,
)


VIDEO_PREVIEW_WIDTH = 360


def render_youtube_publication(video_path: Path | None, project: VideoProject | None) -> None:
    st.subheader("Publicar no YouTube")
    st.caption("Você pode conectar e selecionar contas antes de gerar o vídeo. O upload só acontece após a confirmação abaixo.")

    try:
        accounts = list_youtube_accounts()
    except YouTubeError as exc:
        st.error(f"Não foi possível carregar as contas do YouTube: {exc}")
        accounts = ()
    accounts_by_id = {account.id: account for account in accounts}
    account_options = [""] + [account.id for account in accounts]
    selected_key = "youtube_selected_account_id"
    if st.session_state.get(selected_key) not in account_options:
        st.session_state[selected_key] = ""
    selected_account_id = st.selectbox(
        "Conta para publicar",
        options=account_options,
        index=0,
        key=selected_key,
        format_func=lambda account_id: (
            "Selecione uma conta para publicar"
            if not account_id
            else accounts_by_id[account_id].display_name
        ),
        help="Nenhuma conta é selecionada automaticamente. Escolha o canal que receberá este MP4.",
    )
    selected_account = accounts_by_id.get(selected_account_id)

    authorization_state = st.session_state.get("youtube_authorization_state")
    authorization = (
        youtube_authorization_status(authorization_state)
        if authorization_state
        else None
    )
    if authorization is None:
        authorization = pending_youtube_authorization()
        if authorization is not None:
            st.session_state["youtube_authorization_state"] = authorization.state

    with st.expander("Conectar ou remover contas do YouTube", expanded=not accounts):
        if authorization is not None and authorization.status == "pending":
            st.info("Há uma conexão do YouTube aguardando conclusão. Conclua o login ou cancele-a para iniciar outra.")
            st.link_button("Abrir autorização do Google", authorization.authorization_url)
            action_left, action_right = st.columns(2)
            if action_left.button("Atualizar após concluir o login", key="youtube_refresh_authorization"):
                st.rerun()
            if action_right.button("Cancelar autorização pendente", key="youtube_cancel_authorization"):
                try:
                    cancel_youtube_authorization(authorization.state)
                    st.session_state.pop("youtube_authorization_state", None)
                    st.rerun()
                except YouTubeError as exc:
                    st.error(f"Não foi possível cancelar a autorização: {exc}")
        elif authorization is not None and authorization.status == "complete" and authorization.account is not None:
            st.session_state.pop("youtube_authorization_state", None)
            st.success(f"Conta conectada: {authorization.account.display_name}")
            st.rerun()
        elif authorization is not None:
            st.session_state.pop("youtube_authorization_state", None)
            st.error(authorization.error or "A conexão com o YouTube não foi concluída.")

        if not is_oauth_configured():
            st.info(
                "Para conectar uma conta, coloque o JSON do cliente OAuth em "
                "`input/youtube/client_secret.json` e reconstrua/inicie o app."
            )
        elif authorization is None or authorization.status != "pending":
            label = st.text_input(
                "Apelido local da conta (opcional)",
                placeholder="Ex.: Canal de ciência",
                key="youtube_new_account_label",
                help="Este apelido aparece apenas neste computador; o título do canal vem da conta autorizada.",
            )
            if st.button("Conectar nova conta", key="youtube_connect_account"):
                try:
                    authorization = start_youtube_authorization(label)
                    st.session_state["youtube_authorization_state"] = authorization.state
                    st.rerun()
                except YouTubeError as exc:
                    st.error(f"Não foi possível iniciar a conexão: {exc}")

        if selected_account is not None:
            if st.button("Remover conexão local desta conta", key="youtube_remove_account"):
                try:
                    remove_youtube_account(selected_account.id)
                    st.session_state[selected_key] = ""
                    st.success("A conexão local foi removida. Para revogar o acesso no Google, use a página de conexões da conta.")
                    st.rerun()
                except YouTubeError as exc:
                    st.error(f"Não foi possível remover a conexão: {exc}")

    if project is None:
        st.info("Envie um projeto JSON válido para revisar os metadados e habilitar a publicação depois da geração.")
        return
    if project.youtube is None:
        st.warning("Este projeto não possui o bloco youtube. Adicione os metadados antes de publicar.")
        return
    if video_path is None:
        st.info("Conexões e seleção de conta já estão disponíveis. Gere um Short para liberar a revisão e o botão de publicação.")
        return

    try:
        previous_publication = load_youtube_publication(video_path)
    except YouTubeError as exc:
        st.error(f"Não foi possível ler o registro de publicação: {exc}")
        previous_publication = None
    captions_requested = project.youtube.captions.enabled
    caption_srt_path = video_path.with_suffix(".srt")
    captions_ready = not captions_requested or caption_srt_path.is_file()
    if previous_publication is not None:
        st.success("Este MP4 já foi enviado ao YouTube.")
        st.link_button("Abrir vídeo publicado", previous_publication.video_url)
        if not captions_requested or previous_publication.caption is not None:
            if previous_publication.caption is not None:
                st.success(
                    "A faixa de legendas também foi enviada "
                    f"em {previous_publication.caption.format.upper()} ({previous_publication.caption.language})."
                )
            return
        st.warning("O MP4 já foi enviado, mas a faixa de legendas ainda está pendente. Você pode enviá-la abaixo.")

    with st.expander("Revisar metadados que serão enviados", expanded=False):
        st.write(f"**Título:** {project.title}")
        st.write(f"**Privacidade:** {project.youtube.status.privacy_status}")
        st.write(f"**Categoria:** {project.youtube.category_id}")
        st.write(f"**Descrição:** {project.youtube.description or '(vazia)'}")
        st.write("**Tags:** " + (", ".join(project.youtube.tags) or "(nenhuma)"))
        st.write(
            "**Mídia sintética declarada:** "
            + ("sim" if project.youtube.status.contains_synthetic_media else "não")
        )
        if captions_requested:
            st.write(
                "**Legenda fechada:** "
                f"{project.youtube.captions.format.upper()} em {project.youtube.captions.language}."
            )
            if captions_ready:
                st.caption("A faixa será enviada depois que o YouTube aceitar o MP4. As legendas visuais já incorporadas no vídeo não são alteradas.")
            else:
                st.error("A publicação pede legenda, mas o SRT desta renderização não existe. Gere novamente com as legendas ativadas.")
        else:
            st.caption("Este projeto publicará apenas o MP4; não há faixa de legenda solicitada no bloco youtube.")

    if selected_account is not None:
        st.info(f"Destino selecionado: **{selected_account.channel_title}**.")
    confirmation = st.checkbox(
        "Confirmo o canal, os metadados, os direitos de publicação e as declarações acima.",
        value=False,
        key=f"youtube_publish_confirmation_{file_sha256(video_path)[:16]}",
    )
    can_publish = selected_account is not None and confirmation and captions_ready
    if previous_publication is not None:
        publish_label = "Enviar legenda ao vídeo já publicado"
    elif captions_requested:
        publish_label = "Publicar MP4 e legenda no YouTube"
    else:
        publish_label = "Publicar MP4 no YouTube"
    if st.button(
        publish_label,
        type="primary",
        disabled=not can_publish,
        key=f"youtube_publish_{video_path.parent.name}",
        use_container_width=True,
    ):
        upload_progress = st.progress(0.0, text="Preparando publicação no YouTube…")

        def update_upload_progress(message: str, fraction: float | None = None) -> None:
            if fraction is None:
                upload_progress.progress(0.0, text=message)
            else:
                upload_progress.progress(min(1.0, max(0.0, fraction)), text=message)

        try:
            spinner_text = (
                "Enviando a faixa de legendas para o YouTube…"
                if previous_publication is not None
                else "Enviando o MP4 para o YouTube…"
            )
            with st.spinner(spinner_text):
                publication = publish_to_youtube(
                    project,
                    video_path,
                    selected_account.id,
                    progress=update_upload_progress,
                )
            upload_progress.progress(1.0, text="Upload concluído")
            if publication.caption is not None:
                st.success("MP4 e faixa de legendas enviados. O YouTube pode continuar processando os dois itens antes de disponibilizá-los.")
            else:
                st.success("Upload concluído. O YouTube pode continuar processando o vídeo antes de disponibilizá-lo.")
            st.link_button("Abrir vídeo no YouTube", publication.video_url, type="primary")
        except YouTubeAlreadyPublishedError as exc:
            st.info(str(exc))
        except YouTubeError as exc:
            st.error(f"A publicação não foi concluída: {exc}")


st.set_page_config(page_title="Local Short Studio", page_icon="🎬", layout="wide")

# Mantém a geração inteira na primeira aba sem duplicar seu fluxo legado.
# O proxy preserva session_state do módulo Streamlit e direciona os widgets para
# o container da aba de geração; a aba de resultados usa seu próprio contexto.
_streamlit_module = st
generation_tab, results_tab = _streamlit_module.tabs(["Gerar Short", "Resultados do canal"])


class _TabStreamlitProxy:
    def __init__(self, container, module) -> None:
        self._container = container
        self._module = module

    def __getattr__(self, name: str):
        if name == "session_state":
            return self._module.session_state
        try:
            return getattr(self._container, name)
        except AttributeError:
            return getattr(self._module, name)


st = _TabStreamlitProxy(generation_tab, _streamlit_module)
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


def active_workspace() -> ProjectWorkspace | None:
    raw_root = st.session_state.get("workspace_root")
    if not raw_root:
        return None
    try:
        return ProjectWorkspace.open(raw_root)
    except WorkspaceError:
        st.session_state.pop("workspace_root", None)
        return None


with st.expander("Projetos salvos para revisão", expanded=False):
    saved_workspaces = ProjectWorkspace.list()
    if saved_workspaces:
        options = [item.workspace_id for item in saved_workspaces]
        selected_workspace_id = st.selectbox(
            "Retomar projeto salvo",
            options=options,
            format_func=lambda item: next(
                f"{entry.title} · atualizado {entry.updated_at[:19].replace('T', ' ')}"
                for entry in saved_workspaces if entry.workspace_id == item
            ),
        )
        if st.button("Abrir projeto salvo", key="open_saved_workspace"):
            selected_summary = next(item for item in saved_workspaces if item.workspace_id == selected_workspace_id)
            try:
                opened = ProjectWorkspace.open(selected_summary.root)
                restored_project = opened.load_project()
                st.session_state["workspace_root"] = str(opened.root)
                st.session_state["workspace_project_text"] = restored_project.to_json()
                st.session_state["workspace_images_zip"] = opened.build_image_zip(restored_project)
                st.rerun()
            except Exception as exc:
                st.error(f"Não foi possível retomar este projeto: {exc}")
    else:
        st.caption("Ainda não há projetos salvos. O primeiro preview ou render completo cria um workspace persistente.")

workspace = active_workspace()
sample_project = example_project()
sample_text = sample_project.to_json()
uploaded = st.file_uploader("1. Importe o projeto de cenas (.json)", type=["json"])
project_uploaded = uploaded is not None or workspace is not None
if workspace is not None and "workspace_project_text" in st.session_state:
    project_text = str(st.session_state["workspace_project_text"])
elif workspace is not None:
    try:
        project_text = workspace.load_project().to_json()
    except WorkspaceError as exc:
        st.error(str(exc))
        project_text = ""
elif uploaded:
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

with st.expander("Revisar roteiro e metadados", expanded=False):
    project_text = st.text_area(
        "JSON do projeto",
        value=project_text,
        height=430,
        help=(
            "Cada cena precisa de narration e image_path. O campo opcional shots aceita de 2 a 4 "
            "planos com imagens do ZIP; transition_to_next escolhe a passagem para a cena seguinte."
        ),
    )

parsed: VideoProject | None = None
try:
    if project_text.strip():
        parsed = VideoProject.from_json_text(project_text)
except Exception as exc:
    st.error(f"Projeto inválido: {exc}")

if parsed is not None:
    parsed_plan_count = len(project_image_paths(parsed))
    st.caption(f"Projeto válido: {len(parsed.scenes)} cenas e {parsed_plan_count} planos visuais.")
    transition_summaries = []
    transition_labels = {
        "cut": "corte seco",
        "crossfade": "dissolvência",
        "fade_black": "passagem pelo preto",
    }
    for scene in parsed.scenes[:-1]:
        transition = scene.transition_to_next
        if transition is None:
            transition_summaries.append(f"{scene.id}: dissolvência padrão")
            continue
        duration = (
            f" ({transition.duration_seconds:.2f}s)"
            if transition.duration_seconds is not None
            else " (duração padrão)" if transition.type != "cut" else ""
        )
        transition_summaries.append(
            f"{scene.id}: {transition_labels[transition.type]}{duration}"
        )
    if transition_summaries:
        st.caption("Transições entre cenas: " + " · ".join(transition_summaries))

input_root = Path(os.getenv("INPUT_DIR", "/workspace/input"))
music_catalog: MusicCatalog | None = None
music_catalog_error: str | None = None
try:
    music_catalog = load_music_catalog(input_root)
except MusicCatalogError as exc:
    music_catalog_error = str(exc)

images_upload = st.file_uploader(
    "2. Importe as imagens das cenas (.zip)",
    type=["zip"],
    help="O ZIP pode conter imagens na raiz ou em uma única subpasta. Use PNG, JPG, JPEG ou WebP.",
)
if images_upload is not None:
    image_zip_data: bytes | None = images_upload.getvalue()
elif workspace is not None:
    try:
        image_zip_data = bytes(st.session_state.get("workspace_images_zip") or workspace.build_image_zip(parsed) if parsed else b"")
    except Exception as exc:
        st.error(f"Não foi possível recuperar as imagens salvas: {exc}")
        image_zip_data = None
else:
    image_zip_data = None

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
    value=True,
    help=(
        "Usa Montserrat ExtraBold em maiúsculas, blocos de até três palavras, entrada em pop e destaque progressivo. "
        "Desmarcado: não queima texto no vídeo."
    ),
)
if parsed is not None and parsed.youtube is not None and parsed.youtube.captions.enabled and not captions_enabled:
    st.warning(
        "O bloco youtube solicita uma faixa de legenda, mas as legendas locais estão desativadas. "
        "Ative-as antes de gerar para produzir o SRT necessário à publicação."
    )
image_effects_enabled = st.checkbox(
    "Aplicar movimentos suaves nas imagens",
    value=True,
    help="Desmarque para testar a narração e as transições sem aplicar zoom ou panorâmica. As transições entre cenas continuam ativas.",
)
caption_size_col, caption_height_col = st.columns(2)
caption_font_size = caption_size_col.slider(
    "Tamanho da fonte da legenda",
    min_value=36,
    max_value=120,
    value=DEFAULT_CAPTION_FONT_SIZE,
    step=2,
    disabled=not captions_enabled,
    help="Tamanho da fonte no vídeo vertical de 1080 × 1920 pixels.",
)
caption_height_percent = caption_height_col.slider(
    "Altura da legenda na tela",
    min_value=15,
    max_value=75,
    value=DEFAULT_CAPTION_HEIGHT_PERCENT,
    step=1,
    format="%d%%",
    disabled=not captions_enabled,
    help="0% corresponde à base, 50% ao centro e valores maiores sobem a legenda.",
)
voice_reference_upload = None
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
    st.info("Chatterbox usa o checkpoint dedicado pt-BR. Sem referência, usa a voz interna; com um áudio, tenta reproduzir a sua voz.")
    voice_reference_upload = st.file_uploader(
        "Áudio de referência da sua voz (opcional)",
        type=["wav", "mp3", "flac", "ogg"],
        help="Use 5–10 segundos de voz limpa, em português brasileiro, sem música, eco ou outras pessoas.",
    )
    cb_left, cb_middle, cb_right = st.columns(3)
    chatterbox_exaggeration = cb_left.slider("Expressividade", 0.25, 1.0, 0.5, 0.05)
    chatterbox_cfg = cb_middle.slider("Controle de ritmo", 0.2, 0.8, 0.5, 0.05)
    chatterbox_temperature = cb_right.slider("Variação", 0.3, 1.2, 0.8, 0.05)
    chatterbox_settings = {
        "exaggeration": chatterbox_exaggeration,
        "cfg_weight": chatterbox_cfg,
        "temperature": chatterbox_temperature,
    }

st.subheader("Trilha sonora")
project_soundtrack_valid = True
json_track = None
if parsed is not None and parsed.soundtrack is not None:
    if music_catalog is None:
        st.error(music_catalog_error or "O catálogo local não pôde ser carregado.")
        project_soundtrack_valid = False
    else:
        try:
            json_track = music_catalog.get(parsed.soundtrack.track_id, verify_sha256=True)
            if parsed.soundtrack.volume_percent not in {0, json_track.recommended_volume_percent}:
                raise MusicCatalogError(
                    f"O JSON pede {parsed.soundtrack.volume_percent}%, mas deve usar 0% para silêncio "
                    f"explícito ou os {json_track.recommended_volume_percent}% recomendados para {json_track.id}."
                )
        except MusicCatalogError as exc:
            st.error(f"Trilha do projeto inválida: {exc}")
            project_soundtrack_valid = False

music_source_options = ["none", "upload"]
if music_catalog is not None and music_catalog.editorial_tracks():
    music_source_options.insert(1, "catalog")
if parsed is not None and parsed.music_path:
    music_source_options.insert(0, "legacy")
if parsed is not None and parsed.soundtrack is not None:
    music_source_options.insert(0, "json")

music_source_labels = {
    "json": "Aceitar a faixa definida no JSON",
    "catalog": "Escolher outra faixa do catálogo local",
    "legacy": "Usar music_path legado do JSON",
    "upload": "Enviar um arquivo manualmente",
    "none": "Sem música nesta geração",
}
music_source = st.selectbox(
    "Música efetiva nesta geração",
    options=music_source_options,
    format_func=lambda value: music_source_labels[value],
    help=(
        "Precedência aplicada: upload selecionado, faixa escolhida aqui, faixa do JSON, "
        "music_path legado e, por fim, sem música. O project.json original não é reescrito."
    ),
)

selected_catalog_track = json_track if music_source == "json" else None
selected_catalog_track_id: str | None = None
if music_source == "catalog" and music_catalog is not None:
    editorial_tracks = music_catalog.editorial_tracks()
    track_ids = [track.id for track in editorial_tracks]
    preferred_id = json_track.id if json_track and json_track.id in track_ids else track_ids[0]
    selected_catalog_track_id = st.selectbox(
        "Faixa do catálogo",
        options=track_ids,
        index=track_ids.index(preferred_id),
        format_func=lambda track_id: next(
            f"{track.title} · {track.category} · {track.recommended_volume_percent}%"
            for track in editorial_tracks if track.id == track_id
        ),
    )
    selected_catalog_track = music_catalog.get(selected_catalog_track_id)

if selected_catalog_track is not None:
    artist = selected_catalog_track.artist_candidate or "autor não identificado"
    st.info(
        f"**{selected_catalog_track.title}** — {artist}  \n"
        f"Categoria: `{selected_catalog_track.category}` · "
        f"Uso estimado: {selected_catalog_track.best_for_estimate or 'não informado'} · "
        f"Duração: {selected_catalog_track.duration_seconds:.1f}s · "
        f"Volume recomendado: {selected_catalog_track.recommended_volume_percent}% · "
        f"Licença: `{selected_catalog_track.license_status}`"
    )
    if selected_catalog_track.license_status == "unverified":
        st.warning(
            "Licença, origem e atribuição não foram comprovadas. A renderização local serve para revisão; "
            "confirme os direitos antes de publicar."
        )
    else:
        st.caption(f"Estado de licença informado no catálogo: {selected_catalog_track.license_status}")

music_upload = None
if music_source == "upload":
    music_upload = st.file_uploader(
        "Música de fundo manual (com direitos de uso)",
        type=["mp3", "wav", "m4a", "aac"],
    )

catalog_volume = selected_catalog_track is not None
recommended_volume = (
    selected_catalog_track.recommended_volume_percent if selected_catalog_track else 12
)
initial_music_volume = (
    parsed.soundtrack.volume_percent
    if music_source == "json" and parsed is not None and parsed.soundtrack is not None
    else recommended_volume
)
music_volume_percent = st.slider(
    "Volume da música",
    min_value=0,
    max_value=max(1, recommended_volume) if catalog_volume else 100,
    value=initial_music_volume,
    step=1,
    format="%d%%",
    disabled=(music_source == "none" or (music_source == "upload" and music_upload is None) or recommended_volume == 0),
    key=f"music_volume_{music_source}_{selected_catalog_track.id if selected_catalog_track else 'manual'}",
    help=(
        "Para uma faixa catalogada, o controle permite apenas manter ou reduzir o teto recomendado; "
        "o app ainda pode baixar o ganho depois de medir a voz. Upload e music_path mantêm o controle legado."
    ),
)

zip_validation: ImageZipValidation | None = None
if image_zip_data is None:
    st.info("Envie o ZIP de imagens para validar o mapeamento das cenas.")
elif parsed is not None:
    try:
        required_images = project_image_paths(parsed)
        zip_validation = validate_image_zip(image_zip_data, required_images)
        st.success(
            f"ZIP válido: {zip_validation.image_count} imagens encontradas para "
            f"{len(parsed.scenes)} cenas e {len(required_images)} planos."
        )
        st.caption("Arquivos encontrados: " + ", ".join(zip_validation.found_names))
        if any(scene.shots is not None for scene in parsed.scenes):
            st.info(
                "Este projeto usa múltiplos planos. O Whisper será executado para alinhar as trocas de imagem, "
                "mesmo se as legendas visuais estiverem desativadas."
            )
        for warning in zip_validation.warnings:
            st.warning(warning)
    except ImageZipError as exc:
        st.error(f"ZIP de imagens inválido: {exc}")

manual_music_ready = music_source != "upload" or music_upload is not None
can_generate = (
    project_uploaded
    and parsed is not None
    and image_zip_data is not None
    and zip_validation is not None
    and project_soundtrack_valid
    and manual_music_ready
)


def effective_project() -> VideoProject:
    project = VideoProject.from_json_text(project_text)
    project.captions.enabled = captions_enabled
    if tts_engine == "kokoro":
        project.voice = voice
        project.speech_speed = speech_speed
    return project


def effective_manual_music_path() -> Path | None:
    manual_music_path = None
    if music_source == "upload" and music_upload is not None:
        music_dir = input_root / "music"
        music_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(music_upload.name).suffix.lower() or ".mp3"
        manual_music_path = music_dir / f"background{suffix}"
        manual_music_path.write_bytes(music_upload.getvalue())
    return manual_music_path


def workspace_for(project: VideoProject) -> ProjectWorkspace:
    current = active_workspace()
    if current is None:
        current = ProjectWorkspace.create(project.title)
        st.session_state["workspace_root"] = str(current.root)
    st.session_state["workspace_project_text"] = project.to_json()
    return current


def editing_pipeline(current_workspace: ProjectWorkspace, update_progress) -> WorkspacePipeline:
    return WorkspacePipeline(
        current_workspace,
        progress=update_progress,
        tts_engine=tts_engine,
        chatterbox_settings=chatterbox_settings,
        image_effects_enabled=image_effects_enabled,
        music_volume=music_volume_percent / 100.0,
        disable_music=music_source == "none",
        manual_music_path=effective_manual_music_path(),
        catalog_track_id=selected_catalog_track_id if music_source == "catalog" else None,
        catalog_volume_percent=music_volume_percent if music_source in {"catalog", "json"} else None,
        caption_font_size=caption_font_size,
        caption_height_percent=caption_height_percent,
    )


def scene_camera_controls(current_workspace: ProjectWorkspace, key: str, image_name: str, camera: Camera | None) -> dict[str, object] | None:
    enabled = st.checkbox("Câmera explícita", value=camera is not None, key=f"{key}_enabled")
    if not enabled:
        return None
    source = camera.model_dump(mode="json") if camera else {
        "start": {"focus_x": 0.5, "focus_y": 0.5, "zoom": 1.0},
        "end": {"focus_x": 0.5, "focus_y": 0.5, "zoom": 1.0},
    }
    cols = st.columns(3)
    start_x = cols[0].slider("Foco X início", 0.0, 1.0, float(source["start"]["focus_x"]), 0.01, key=f"{key}_sx")
    start_y = cols[1].slider("Foco Y início", 0.0, 1.0, float(source["start"]["focus_y"]), 0.01, key=f"{key}_sy")
    start_zoom = cols[2].slider("Zoom início", 1.0, 1.35, float(source["start"]["zoom"]), 0.01, key=f"{key}_sz")
    cols = st.columns(3)
    end_x = cols[0].slider("Foco X fim", 0.0, 1.0, float(source["end"]["focus_x"]), 0.01, key=f"{key}_ex")
    end_y = cols[1].slider("Foco Y fim", 0.0, 1.0, float(source["end"]["focus_y"]), 0.01, key=f"{key}_ey")
    end_zoom = cols[2].slider("Zoom fim", 1.0, 1.35, float(source["end"]["zoom"]), 0.01, key=f"{key}_ez")
    payload: dict[str, object] = {"start": {"focus_x": start_x, "focus_y": start_y, "zoom": start_zoom}, "end": {"focus_x": end_x, "focus_y": end_y, "zoom": end_zoom}, "easing": "quintic"}
    try:
        with Image.open(BytesIO(current_workspace.image_bytes(image_name))) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
        parsed_camera = Camera.model_validate(payload)
        previews = st.columns(2)
        for column, label, pose in ((previews[0], "Início", parsed_camera.start), (previews[1], "Fim", parsed_camera.end)):
            crop = camera_crop_rect(image.width, image.height, 1080, 1920, pose)
            box = (round(crop.x), round(crop.y), round(crop.right), round(crop.bottom))
            column.image(image.crop(box), caption=f"{label}: recorte efetivo")
    except Exception as exc:
        st.caption(f"Prévia do enquadramento indisponível: {exc}")
    return payload


current_workspace = active_workspace()
if current_workspace is None and can_generate:
    if st.button("Salvar projeto para editar e retomar depois", use_container_width=True):
        try:
            project_to_save = effective_project()
            current_workspace = workspace_for(project_to_save)
            current_workspace.import_image_zip(image_zip_data, project_to_save)
            st.session_state["workspace_images_zip"] = current_workspace.build_image_zip(project_to_save)
            st.rerun()
        except Exception as exc:
            st.exception(exc)

if current_workspace is not None and parsed is not None:
    st.subheader("Revisar cenas e reaproveitar artefatos")
    current_project = effective_project()
    export_columns = st.columns(2)
    export_columns[0].download_button("Exportar JSON efetivo", data=current_project.to_json(), file_name="modelo_projeto.json", mime="application/json")
    try:
        export_columns[1].download_button("Exportar ZIP das imagens usadas", data=current_workspace.build_image_zip(current_project), file_name="imagens_cenas.zip", mime="application/zip")
    except Exception as exc:
        export_columns[1].warning(f"ZIP indisponível: {exc}")
    image_choices = list(current_workspace.image_names())
    motions = ["slow_push_in", "slow_pull_out", "pan_left", "pan_right", "pan_up", "pan_down", "static", "auto"]
    for scene_index, scene in enumerate(current_project.scenes):
        with st.expander(f"Cena {scene_index + 1}: {scene.id}"):
            narration = st.text_area("Narração da cena", scene.narration, key=f"review_{scene.id}_narration")
            shots = scene.visual_shots()
            first_choices = image_choices if scene.image_path in image_choices else [scene.image_path] + image_choices
            primary_image = st.selectbox("Imagem principal", first_choices, index=first_choices.index(scene.image_path), key=f"review_{scene.id}_image")
            replacement = st.file_uploader("Substituir imagem principal", type=["png", "jpg", "jpeg", "webp"], key=f"review_{scene.id}_upload")
            plan_count = st.select_slider(
                "Planos desta cena",
                options=[1, 2, 3, 4],
                value=len(shots),
                help="Com dois ou mais planos, cada plano adicional precisa começar em uma frase-âncora da narração.",
                key=f"review_{scene.id}_plan_count",
            )
            scene_camera = scene_camera_controls(current_workspace, f"review_{scene.id}", primary_image, scene.camera)
            plan_inputs: list[dict[str, object]] = [{
                "image_path": primary_image,
                "motion": st.selectbox("Movimento do plano 1", motions, index=motions.index(shots[0].motion), key=f"review_{scene.id}_motion_0"),
                "camera": None,
                "start_phrase": None,
            }]
            for shot_index in range(1, plan_count):
                existing = shots[shot_index] if shot_index < len(shots) else None
                default_image = existing.image_path if existing else primary_image
                choices = image_choices if default_image in image_choices else [default_image] + image_choices
                st.markdown(f"**Plano {shot_index + 1}**")
                shot_image = st.selectbox(
                    "Imagem",
                    choices,
                    index=choices.index(default_image),
                    key=f"review_{scene.id}_image_{shot_index}",
                )
                shot_upload = st.file_uploader(
                    "Enviar outra imagem para este plano",
                    type=["png", "jpg", "jpeg", "webp"],
                    key=f"review_{scene.id}_upload_{shot_index}",
                )
                anchor = st.text_input(
                    "Frase-âncora de início",
                    existing.start_phrase if existing and existing.start_phrase else "",
                    key=f"review_{scene.id}_anchor_{shot_index}",
                )
                motion = st.selectbox(
                    "Movimento",
                    motions,
                    index=motions.index(existing.motion if existing else "auto"),
                    key=f"review_{scene.id}_motion_{shot_index}",
                )
                shot_camera = scene_camera_controls(
                    current_workspace,
                    f"review_{scene.id}_shot_{shot_index}",
                    shot_image,
                    existing.camera if existing else None,
                )
                plan_inputs.append({
                    "image_path": shot_image,
                    "replacement": shot_upload,
                    "motion": motion,
                    "camera": shot_camera,
                    "start_phrase": anchor,
                })
            transition_data: dict[str, object] | None = None
            if scene_index < len(current_project.scenes) - 1:
                existing_transition = scene.transition_to_next
                transition_type = st.selectbox(
                    "Transição para a próxima cena",
                    ["cut", "crossfade", "fade_black"],
                    index=["cut", "crossfade", "fade_black"].index(existing_transition.type if existing_transition else "cut"),
                    key=f"review_{scene.id}_transition",
                )
                if transition_type == "cut":
                    transition_data = {"type": "cut"}
                else:
                    transition_data = {
                        "type": transition_type,
                        "duration_seconds": st.slider(
                            "Duração da transição (s)", 0.15, 0.45,
                            float(existing_transition.duration_seconds if existing_transition and existing_transition.duration_seconds else 0.25),
                            0.01, key=f"review_{scene.id}_transition_seconds",
                        ),
                    }
            if st.button("Salvar edição desta cena", key=f"save_scene_{current_workspace.workspace_id}_{scene.id}"):
                try:
                    project_data = current_project.model_dump(mode="json")
                    target_scene = project_data["scenes"][scene_index]
                    if replacement is not None:
                        primary_image = current_workspace.store_uploaded_image(replacement.name, replacement.getvalue())
                    plan_inputs[0]["image_path"] = primary_image
                    for plan in plan_inputs[1:]:
                        uploaded = plan.pop("replacement", None)
                        if uploaded is not None:
                            plan["image_path"] = current_workspace.store_uploaded_image(uploaded.name, uploaded.getvalue())
                    target_scene["narration"] = narration
                    target_scene["image_path"] = primary_image
                    target_scene["camera"] = scene_camera
                    target_scene["motion"] = plan_inputs[0]["motion"]
                    target_scene["transition_to_next"] = transition_data
                    if plan_count == 1:
                        target_scene["shots"] = None
                    else:
                        target_scene["shots"] = [
                            {
                                "image_path": plan["image_path"],
                                "motion": plan["motion"],
                                **({"camera": plan["camera"]} if plan["camera"] is not None else {}),
                                **({"start_phrase": plan["start_phrase"]} if index else {}),
                            }
                            for index, plan in enumerate(plan_inputs)
                        ]
                    updated = VideoProject.model_validate(project_data)
                    current_workspace.save_project(updated)
                    st.session_state["workspace_project_text"] = updated.to_json()
                    st.session_state["workspace_images_zip"] = current_workspace.build_image_zip(updated)
                    st.success("Edição salva; texto invalida apenas a voz/alinhamento desta cena, e câmera/imagem só o visual.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Não foi possível salvar: {exc}")
            if st.button("Prévia animada desta cena", key=f"scene_preview_{current_workspace.workspace_id}_{scene.id}"):
                try:
                    result = editing_pipeline(current_workspace, lambda *_args: None).preview(current_project, current_workspace.build_image_zip(current_project), scene_index=scene_index, resolution=960)
                    st.video(str(result.video_path), width=VIDEO_PREVIEW_WIDTH)
                except Exception as exc:
                    st.exception(exc)
            if st.button("Regenerar apenas esta voz", key=f"scene_voice_{current_workspace.workspace_id}_{scene.id}"):
                try:
                    editing_pipeline(current_workspace, lambda *_args: None).run(current_project, current_workspace.build_image_zip(current_project), force_regenerate_scene_ids=[scene.id])
                    st.success("Uma nova realização foi gerada e será reutilizada nos próximos renders.")
                except Exception as exc:
                    st.exception(exc)


preview_left, preview_right = st.columns((1, 1))
preview_resolution = preview_left.selectbox(
    "Resolução da prévia do gancho",
    options=[960, 1920],
    format_func=lambda value: "Rápida — 540 × 960" if value == 960 else "Final — 1080 × 1920",
    help="A prévia usa a mesma proporção, taxa de quadros, câmera, música e legendas do Short final.",
)
preview_requested = preview_right.button("Prévia do gancho", disabled=not can_generate, use_container_width=True)
if preview_requested:
    project = effective_project()
    progress_bar = st.progress(0.0, text="Preparando a prévia…")
    status_text = st.empty()
    started = time.perf_counter()

    def update_preview_progress(message: str, fraction: float | None = None):
        status_text.info(f"{message}  ·  decorrido: {time.perf_counter() - started:.0f}s")
        if fraction is not None:
            progress_bar.progress(min(1.0, max(0.0, fraction)), text=message)

    try:
        current_workspace = workspace_for(project)
        with st.spinner("Gerando vídeo real da abertura…"):
            result = editing_pipeline(current_workspace, update_preview_progress).preview(
                project,
                image_zip_data,
                resolution=preview_resolution,
                voice_reference=voice_reference_upload.getvalue() if voice_reference_upload else None,
                voice_reference_name=voice_reference_upload.name if voice_reference_upload else None,
            )
        st.session_state["hook_preview_path"] = str(result.video_path)
        st.success(f"Prévia pronta: {result.duration_seconds:.1f}s.")
        if result.duration_seconds > 6.0:
            st.warning("A abertura passa de cerca de seis segundos. Ela não foi cortada; considere enxugar a primeira cena.")
        if result.preview_music_may_change:
            st.info("O ganho musical foi medido só nesta abertura; o Short completo recalcula o ganho contra toda a narração.")
    except Exception as exc:
        status_text.error("A prévia parou. Veja a mensagem abaixo.")
        st.exception(exc)

preview_path = Path(st.session_state["hook_preview_path"]) if st.session_state.get("hook_preview_path") else None
if preview_path is not None and preview_path.is_file():
    st.caption("Prévia — este MP4 não aparece no seletor de publicação.")
    st.video(str(preview_path), width=VIDEO_PREVIEW_WIDTH)
    st.download_button("Baixar prévia do gancho", data=preview_path.read_bytes(), file_name=preview_path.name, mime="video/mp4")

if st.button("Gerar Short", type="primary", disabled=not can_generate, use_container_width=True):
    project = effective_project()

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
            current_workspace = active_workspace()
            if current_workspace is None:
                # Preserve the original one-click flow and its output layout.
                # Persistence and selective rendering begin only after the user
                # explicitly saves a workspace or requests a preview.
                output_video = ShortPipeline(
                    progress=update_progress,
                    tts_engine=tts_engine,
                    chatterbox_settings=chatterbox_settings,
                    image_effects_enabled=image_effects_enabled,
                    music_volume=music_volume_percent / 100.0,
                    disable_music=music_source == "none",
                    manual_music_path=effective_manual_music_path(),
                    catalog_track_id=selected_catalog_track_id if music_source == "catalog" else None,
                    catalog_volume_percent=music_volume_percent if music_source in {"catalog", "json"} else None,
                    caption_font_size=caption_font_size,
                    caption_height_percent=caption_height_percent,
                ).run(
                    project,
                    image_zip_data,
                    voice_reference=voice_reference_upload.getvalue() if voice_reference_upload else None,
                    voice_reference_name=voice_reference_upload.name if voice_reference_upload else None,
                )
            else:
                result = editing_pipeline(current_workspace, update_progress).run(
                    project,
                    image_zip_data,
                    voice_reference=voice_reference_upload.getvalue() if voice_reference_upload else None,
                    voice_reference_name=voice_reference_upload.name if voice_reference_upload else None,
                )
                output_video = result.video_path
        status_text.success("Short finalizado.")
        progress_bar.progress(1.0, text="Pronto")
        st.session_state["youtube_output_video_path"] = str(output_video)
        st.session_state["youtube_output_project_json"] = project.to_json()
        st.session_state["performance_output_effective"] = {
            "tts_engine": tts_engine,
            "chatterbox": chatterbox_settings or {},
            "music_source": music_source,
            "catalog_track_id": selected_catalog_track_id,
            "music_volume_percent": music_volume_percent,
        }
        st.video(str(output_video), width=VIDEO_PREVIEW_WIDTH)
        st.download_button(
            "Baixar MP4",
            data=output_video.read_bytes(),
            file_name=output_video.name,
            mime="video/mp4",
            type="primary",
        )
        project_dir = output_video.parent
        if current_workspace is None:
            st.write(f"Arquivos salvos em: `{project_dir}`")
        else:
            st.write(f"Arquivos salvos em: `{project_dir}` (workspace persistente: `{current_workspace.root}`)")
        if captions_enabled:
            srt_path = output_video.with_suffix(".srt")
            if srt_path.exists():
                st.download_button("Baixar legendas SRT", data=srt_path.read_bytes(), file_name=srt_path.name, mime="application/x-subrip")
    except Exception as exc:
        status_text.error("A geração parou. Veja a etapa indicada na mensagem abaixo.")
        st.exception(exc)

stored_video_path = st.session_state.get("youtube_output_video_path")
stored_project_json = st.session_state.get("youtube_output_project_json")
stored_video: Path | None = None
stored_project: VideoProject | None = None
if stored_video_path and stored_project_json:
    stored_video = Path(stored_video_path)
    try:
        stored_project = VideoProject.from_json_text(stored_project_json)
    except Exception:
        st.session_state.pop("youtube_output_video_path", None)
        st.session_state.pop("youtube_output_project_json", None)
        stored_video = None
    else:
        if stored_video.is_file():
            pass
        else:
            st.warning("O MP4 gerado nesta sessão não está mais disponível para publicação.")
            st.session_state.pop("youtube_output_video_path", None)
            st.session_state.pop("youtube_output_project_json", None)
            stored_video = None

_streamlit_module.divider()
with results_tab:
    render_channel_performance(
        input_root,
        available_video=stored_video,
        project=stored_project,
        effective=st.session_state.get("performance_output_effective") or {},
    )

st.divider()
render_youtube_publication(stored_video, stored_project or parsed)

st.divider()
st.markdown("**Fluxo local:** modelo JSON + ZIP → validação → voz pt-BR local → alinhamento quando necessário → FFmpeg → MP4 9:16")

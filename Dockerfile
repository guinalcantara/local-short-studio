FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/workspace \
    MUSIC_LIBRARY_DIR=/workspace/assets/music_library \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl ffmpeg fonts-inter fonts-dejavu-core fontconfig libsndfile1 espeak-ng git \
    && rm -rf /var/lib/apt/lists/*

ARG MONTSERRAT_COMMIT=76fca9fd0bb4ea46583f92e978660f3984ab9442
RUN mkdir -p /usr/local/share/fonts/truetype/montserrat /usr/share/doc/fonts-montserrat \
    && curl --fail --location --retry 3 \
        --output /usr/local/share/fonts/truetype/montserrat/Montserrat-Variable.ttf \
        "https://raw.githubusercontent.com/google/fonts/${MONTSERRAT_COMMIT}/ofl/montserrat/Montserrat%5Bwght%5D.ttf" \
    && curl --fail --location --retry 3 \
        --output /usr/share/doc/fonts-montserrat/OFL.txt \
        "https://raw.githubusercontent.com/google/fonts/${MONTSERRAT_COMMIT}/ofl/montserrat/OFL.txt" \
    && printf '%s  %s\n' \
        '0f7b311b2f3279e4eef9b2f968bcdbab6e28f4daeb1f049f4f278a902bcd82f7' \
        '/usr/local/share/fonts/truetype/montserrat/Montserrat-Variable.ttf' \
        '8b7141c03fa4f8d44e6345d5d4931709290f0f67875e452e95ac1fd3a027802e' \
        '/usr/share/doc/fonts-montserrat/OFL.txt' \
        | sha256sum --check - \
    && fc-cache -f

WORKDIR /workspace
COPY requirements.txt /workspace/requirements.txt
RUN pip install --upgrade pip && pip install -r /workspace/requirements.txt

COPY app /workspace/app
COPY config /workspace/config
COPY assets /workspace/assets

EXPOSE 8501
CMD ["streamlit", "run", "app/ui.py", "--server.address=0.0.0.0", "--server.port=8501", "--browser.gatherUsageStats=false"]

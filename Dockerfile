FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-inter fonts-dejavu-core fontconfig libsndfile1 espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY requirements.txt /workspace/requirements.txt
RUN pip install --upgrade pip && pip install -r /workspace/requirements.txt

COPY app /workspace/app
COPY config /workspace/config
COPY workflows /workspace/workflows
COPY assets /workspace/assets

EXPOSE 8501
CMD ["streamlit", "run", "app/ui.py", "--server.address=0.0.0.0", "--server.port=8501", "--browser.gatherUsageStats=false"]

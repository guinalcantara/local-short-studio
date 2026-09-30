FROM pytorch/pytorch:2.14.0-cuda13.0-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN git clone --depth 1 --branch v0.38.0 https://github.com/Comfy-Org/ComfyUI.git /opt/ComfyUI
WORKDIR /opt/ComfyUI
RUN pip install --upgrade pip && pip install -r requirements.txt

EXPOSE 8188
CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--lowvram"]


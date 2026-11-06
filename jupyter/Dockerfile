FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/home/estudiante/.cache/huggingface \
    TOKENIZERS_PARALLELISM=false

# Cliente psql para inspeccionar la base desde la terminal de Jupyter
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# PyTorch solo CPU: mucho más liviano que la versión con CUDA
# torch y torchvision se instalan JUNTOS desde el mismo indice CPU para que sus versiones coincidan.
# (si torchvision viniera de PyPI, desemparejado de torch, falla con "torchvision::nms does not exist")
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
# Verificacion en tiempo de build: si la importacion falla, la imagen no se construye
RUN python -c "from sentence_transformers import SentenceTransformer; print('sentence-transformers OK')"

# Usuario sin privilegios (UID 1000) para evitar problemas de permisos en las
# carpetas montadas
RUN useradd -m -u 1000 -s /bin/bash estudiante \
    && mkdir -p /home/estudiante/trabajo /home/estudiante/.cache/huggingface \
    && chown -R estudiante:estudiante /home/estudiante

USER estudiante
WORKDIR /home/estudiante/trabajo

EXPOSE 8888

CMD ["sh", "-c", "jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --IdentityProvider.token=\"${JUPYTER_TOKEN}\" --ServerApp.root_dir=/home/estudiante/trabajo"]

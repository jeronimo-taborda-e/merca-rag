"""Configuración central de MercaRAG.

Las credenciales nunca se escriben en el código: Docker las inyecta como variables
de entorno desde el archivo .env (ver docker-compose.yml).
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------- rutas
# notebooks/mercarag/config.py -> raíz del área de trabajo (/home/estudiante/trabajo)
TRABAJO_DIR = Path(os.getenv("MERCARAG_TRABAJO_DIR", Path(__file__).resolve().parents[2]))
DATA_DIR = TRABAJO_DIR / "data"
DOCUMENTOS_DIR = DATA_DIR / "documentos"
IMAGENES_DIR = DATA_DIR / "imagenes"
CONSULTAS_DIR = DATA_DIR / "consultas"
RESULTADOS_DIR = DATA_DIR / "resultados"

# ---------------------------------------------------------------- base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mercarag:mercarag@localhost:5434/mercarag")

# ---------------------------------------------------------------- modelos
# Dos espacios vectoriales (regla de oro del laboratorio: nunca mezclar 384 con 512):
#   * MiniLM multilingüe (384): chunks de texto <-> preguntas de texto
#   * CLIP ViT-B/32 (512): imágenes <-> imágenes y texto (codificador de texto multilingüe)
# Se usa la versión MULTILINGÜE de MiniLM (misma dimensión 384 que all-MiniLM-L6-v2 de la
# Entrega 1) porque los documentos y las preguntas están en español.
MODELO_TEXTO = os.getenv("MODELO_TEXTO", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
MODELO_CLIP_IMAGEN = os.getenv("MODELO_CLIP_IMAGEN", "sentence-transformers/clip-ViT-B-32")
MODELO_CLIP_TEXTO = os.getenv("MODELO_CLIP_TEXTO", "sentence-transformers/clip-ViT-B-32-multilingual-v1")
DIM_TEXTO = 384
DIM_CLIP = 512

# Longitud máxima (en tokens del tokenizador de MiniLM) que el modelo lee de un chunk.
# Lo que pase de aquí se trunca al vectorizar: el experimento de chunking lo reporta.
MAX_SEQ_TEXTO = int(os.getenv("MAX_SEQ_TEXTO", "512"))

# Se antepone el título del documento a cada chunk ANTES de vectorizar (no se guarda así).
# Ayuda a que un chunk como "Conservación: mantener refrigerado..." sepa de qué producto habla.
ANTEPONER_TITULO = True

# ---------------------------------------------------------------- chunking (Entrega 1)
ESTRATEGIAS = ("fijo", "oraciones", "semantico")

PARAMETROS_CHUNKING = {
    # Fixed-size: LangChain TokenTextSplitter (tiktoken cl100k_base)
    "fijo": {"chunk_size": 512, "chunk_overlap": 64, "encoding_name": "cl100k_base"},
    # Sentence-aware: spaCy es_core_news_sm, ventana de 6 oraciones que se solapa 1
    "oraciones": {"max_sentences": 6, "overlap": 1, "spacy_model": "es_core_news_sm"},
    # Semantic: Sentence Transformers; nuevo chunk cuando la similitud coseno entre la
    # oración y el centroide del chunk actual cae por debajo del umbral. Rango 0.60-0.70.
    # thresholds_experimento: 0.60-0.70 son los de la Entrega 1; 0.40-0.55 son de referencia
    # ("rango experimental para después acomodarlo según resultados", Entrega 1).
    # max_tokens: protección para que un chunk no supere lo que MiniLM lee (deja margen
    # para el título que se antepone al vectorizar). None = sin protección.
    # min_tokens: un chunk con menos tokens (p. ej. un título) no se cierra todavía.
    "semantico": {"threshold": 0.65,
                  "thresholds_experimento": [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70],
                  "max_tokens": MAX_SEQ_TEXTO - 32, "min_tokens": 16},
}

# ---------------------------------------------------------------- LLM (Groq, API compatible con OpenAI)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

# Límite de caracteres del contexto que se envía al LLM
MAX_CHARS_CONTEXTO = 6000

# Usuario del sistema con el que se registran las consultas de los notebooks
EMAIL_USUARIO_NOTEBOOK = os.getenv("EMAIL_USUARIO_NOTEBOOK", "empleado1@mercarag.co")

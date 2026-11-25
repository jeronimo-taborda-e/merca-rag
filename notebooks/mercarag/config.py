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
EVALUACION_DIR = DATA_DIR / "evaluacion"
RESULTADOS_DIR = DATA_DIR / "resultados"

# ---------------------------------------------------------------- base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mercarag:mercarag@localhost:5434/mercarag")

# ---------------------------------------------------------------- modelos
# Dos espacios vectoriales (regla de oro: nunca se compara un vector de 384 con uno de 512):
#   * multilingual-e5-small (384): chunks de texto <-> preguntas de texto
#   * CLIP ViT-B/32 (512): imágenes <-> imágenes y texto (codificador de texto multilingüe)
# Los documentos y las preguntas están en español, por eso el modelo de texto es multilingüe.
# e5-small lee hasta 512 tokens, así que los chunks de 256 tokens entran completos.
MODELO_TEXTO = os.getenv("MODELO_TEXTO", "intfloat/multilingual-e5-small")
MODELO_CLIP_IMAGEN = os.getenv("MODELO_CLIP_IMAGEN", "sentence-transformers/clip-ViT-B-32")
MODELO_CLIP_TEXTO = os.getenv("MODELO_CLIP_TEXTO", "sentence-transformers/clip-ViT-B-32-multilingual-v1")
DIM_TEXTO = 384
DIM_CLIP = 512

# e5 se entrenó con prefijos: "passage: " para lo que se guarda y "query: " para lo que se pregunta.
PREFIJO_PASAJE = "passage: "
PREFIJO_CONSULTA = "query: "

# Ventana del modelo de texto, en tokens de SU tokenizador. Ningún chunk la supera (CHECK en la base).
MAX_SEQ_TEXTO = 512

# El título del documento se antepone a cada chunk ANTES de vectorizar (no se guarda así).
# Ayuda a que un chunk como "Conservación: mantener refrigerado..." sepa de qué producto habla.
ANTEPONER_TITULO = True

# Margen para "passage: " + título + tokens especiales: el contenido de un chunk de oraciones o
# semántico se limita a MAX_SEQ_TEXTO - MARGEN_TITULO tokens.
MARGEN_TITULO = 48

# ---------------------------------------------------------------- chunking (Entrega 1, corregida)
ESTRATEGIAS = ("fijo", "oraciones", "semantico")

# Los parámetros se fijan ANTES del experimento y no se ajustan mirando las métricas.
# Todos los tamaños se miden con el tokenizador del modelo de embeddings (no con tiktoken).
PARAMETROS_CHUNKING = {
    # Fixed-size: valores sugeridos por el curso.
    "fijo": {"chunk_size": 256, "chunk_overlap": 32},
    # Sentence-aware: valores sugeridos; el tope de tokens evita que 5 oraciones largas se trunquen.
    "oraciones": {"max_sentences": 5, "overlap": 1, "spacy_model": "es_core_news_sm",
                  "max_tokens": MAX_SEQ_TEXTO - MARGEN_TITULO},
    # Semantic: una oración abre un chunk nuevo cuando su similitud coseno con el centroide del
    # chunk en construcción es menor que 0.80 (punto medio del rango sugerido 0.75-0.85).
    # min_tokens: un título corto ("Cobertura.") no se cierra solo; queda con su primera oración.
    "semantico": {"threshold": 0.80, "max_tokens": MAX_SEQ_TEXTO - MARGEN_TITULO, "min_tokens": 16},
}

# ---------------------------------------------------------------- recuperación y experimento
TOP_K = 5                      # chunks que recibe el LLM en todas las corridas
CONJUNTO_EVALUACION = EVALUACION_DIR / "preguntas.csv"

# ---------------------------------------------------------------- LLM (Groq, API compatible con OpenAI)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
# Temperatura 0 en el experimento: la misma pregunta debe dar la misma respuesta con cada estrategia.
LLM_TEMPERATURA = 0.0
# Modelo juez para las métricas RAGAS (por defecto el mismo LLM)
LLM_EVAL_MODEL = os.getenv("LLM_EVAL_MODEL", LLM_MODEL)

# Límite de caracteres del contexto que se envía al LLM
MAX_CHARS_CONTEXTO = 6000

# Usuario del sistema con el que se registran las consultas de los notebooks
EMAIL_USUARIO_NOTEBOOK = os.getenv("EMAIL_USUARIO_NOTEBOOK", "empleado1@mercarag.co")

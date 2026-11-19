"""Las tres estrategias de chunking de la Entrega 1.

| Estrategia | Herramienta                         | Parámetros del grupo                |
|------------|-------------------------------------|-------------------------------------|
| fijo       | LangChain TokenTextSplitter         | chunk_size = 512, overlap = 64      |
| oraciones  | spaCy (es_core_news_sm)             | max_sentences = 6, overlap = 1      |
| semantico  | Sentence Transformers (MiniLM)      | umbral coseno 0.60 - 0.70           |

Todas reciben el texto limpio de un documento y devuelven una lista de cadenas.
`generar_chunks` las envuelve y agrega los parámetros usados, que se guardan en
embeddings_texto.parametros para poder comparar las estrategias en la misma base.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from . import config


# ------------------------------------------------------------------ utilidades
@lru_cache(maxsize=2)
def _nlp(modelo: str):
    import spacy
    # Solo se necesita la segmentación en oraciones (la hace el parser).
    return spacy.load(modelo, exclude=["ner", "lemmatizer", "attribute_ruler"])


def dividir_oraciones(texto: str, spacy_model: str = "es_core_news_sm") -> list[str]:
    """Separa el texto en oraciones con spaCy.

    Primero se separa por líneas (párrafos, títulos y viñetas) para que una oración
    nunca cruce un salto de párrafo; luego spaCy separa las oraciones de cada línea.
    """
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    nlp = _nlp(spacy_model)
    oraciones = []
    for doc in nlp.pipe(lineas):
        oraciones.extend(s.text.strip() for s in doc.sents if s.text.strip())
    return oraciones


# ------------------------------------------------------------------ 1. tamaño fijo
def chunk_fijo(texto: str, chunk_size: int = 512, chunk_overlap: int = 64,
               encoding_name: str = "cl100k_base") -> list[str]:
    """Ventanas de `chunk_size` tokens (tiktoken) que se solapan `chunk_overlap` tokens.

    No respeta oraciones ni palabras: el corte cae donde se cumplan los tokens.
    """
    from langchain_text_splitters import TokenTextSplitter
    splitter = TokenTextSplitter(encoding_name=encoding_name, chunk_size=chunk_size,
                                 chunk_overlap=chunk_overlap)
    return [c.strip() for c in splitter.split_text(texto) if c.strip()]


# ------------------------------------------------------------------ 2. por oraciones
def ventanas_de_oraciones(oraciones: list[str], max_sentences: int = 6, overlap: int = 1) -> list[str]:
    """Agrupa oraciones completas en ventanas de `max_sentences` que comparten `overlap`."""
    if max_sentences <= overlap:
        raise ValueError("max_sentences debe ser mayor que overlap")
    paso = max_sentences - overlap
    chunks = []
    for inicio in range(0, len(oraciones), paso):
        ventana = oraciones[inicio:inicio + max_sentences]
        chunks.append(" ".join(ventana))
        if inicio + max_sentences >= len(oraciones):
            break
    return chunks


def chunk_oraciones(texto: str, max_sentences: int = 6, overlap: int = 1,
                    spacy_model: str = "es_core_news_sm") -> list[str]:
    return ventanas_de_oraciones(dividir_oraciones(texto, spacy_model), max_sentences, overlap)


# ------------------------------------------------------------------ 3. semántico
def cortes_semanticos(vectores: np.ndarray, threshold: float, n_tokens: list[int] | None = None,
                      max_tokens: int | None = None, min_tokens: int = 0) -> tuple[list[int], np.ndarray]:
    """Decide dónde empieza cada chunk. Devuelve (índices de inicio, similitudes).

    Se recorren las oraciones en orden. Cada oración se compara (coseno) con el
    CENTROIDE del chunk que se está armando (promedio normalizado de sus oraciones):
      * si la similitud es >= threshold, la oración se agrega al chunk;
      * si es < threshold, cambió el tema y la oración abre un chunk nuevo.
    Protecciones:
      * si al agregar la oración el chunk superaría `max_tokens` (lo que MiniLM
        alcanza a leer), también se corta, para no perder contexto por truncamiento;
      * mientras el chunk tenga menos de `min_tokens` (por ejemplo, un título como
        "Cobertura.") no se corta: el título queda pegado a su primera oración.

    similitudes[i] = similitud de la oración i con el chunk anterior (i >= 1).
    """
    n = len(vectores)
    if n == 0:
        return [], np.array([])
    cortes, similitudes = [0], []
    suma = vectores[0].astype(np.float64).copy()
    tokens_chunk = n_tokens[0] if n_tokens else 0
    for i in range(1, n):
        centroide = suma / (np.linalg.norm(suma) + 1e-12)
        sim = float(np.dot(vectores[i], centroide))
        similitudes.append(sim)
        excede = bool(max_tokens and n_tokens and tokens_chunk + n_tokens[i] > max_tokens)
        muy_corto = bool(n_tokens and tokens_chunk < min_tokens)
        if excede or (sim < threshold and not muy_corto):
            cortes.append(i)
            suma = vectores[i].astype(np.float64).copy()
            tokens_chunk = n_tokens[i] if n_tokens else 0
        else:
            suma += vectores[i]
            tokens_chunk += n_tokens[i] if n_tokens else 0
    return cortes, np.array(similitudes)


def chunk_semantico(texto: str, modelos, threshold: float = 0.65, max_tokens: int | None = None,
                    min_tokens: int = 0, spacy_model: str = "es_core_news_sm", oraciones: list[str] | None = None,
                    vectores: np.ndarray | None = None) -> list[str]:
    """Agrupa oraciones consecutivas mientras sigan hablando de lo mismo.

    `modelos.embed_texto` vectoriza las oraciones con MiniLM (Sentence Transformers).
    Se pueden pasar `oraciones` y `vectores` ya calculados para probar varios umbrales
    sin volver a vectorizar.
    """
    if oraciones is None:
        oraciones = dividir_oraciones(texto, spacy_model)
    if not oraciones:
        return []
    if vectores is None:
        vectores = modelos.embed_texto(oraciones)
    n_tokens = [modelos.contar_tokens(o) for o in oraciones] if (max_tokens or min_tokens) else None
    cortes, _ = cortes_semanticos(np.asarray(vectores), threshold, n_tokens, max_tokens, min_tokens)
    limites = cortes + [len(oraciones)]
    return [" ".join(oraciones[a:b]) for a, b in zip(limites[:-1], limites[1:])]


# ------------------------------------------------------------------ envoltorio
def generar_chunks(texto: str, estrategia: str, modelos=None, **params) -> tuple[list[str], dict]:
    """Aplica una estrategia y devuelve (chunks, parámetros usados)."""
    base = dict(config.PARAMETROS_CHUNKING[estrategia])
    base.pop("thresholds_experimento", None)
    base.update(params)
    if estrategia == "fijo":
        chunks = chunk_fijo(texto, **base)
        usados = {**base, "herramienta": "langchain.TokenTextSplitter"}
    elif estrategia == "oraciones":
        chunks = chunk_oraciones(texto, **base)
        usados = {**base, "herramienta": "spaCy"}
    elif estrategia == "semantico":
        if modelos is None:
            raise ValueError("El chunking semántico necesita el modelo de embeddings")
        chunks = chunk_semantico(texto, modelos, **base)
        usados = {**{k: v for k, v in base.items() if k not in ("oraciones", "vectores")},
                  "comparacion": "oracion_vs_centroide",
                  "herramienta": "sentence-transformers", "modelo": config.MODELO_TEXTO}
    else:
        raise ValueError(f"Estrategia desconocida: {estrategia}")
    return chunks, usados

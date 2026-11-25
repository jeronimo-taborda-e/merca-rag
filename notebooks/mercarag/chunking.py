"""Las tres estrategias de chunking de la Entrega 1 (versión corregida).

| Estrategia | Herramienta                                   | Parámetros (fijados antes del experimento) |
|------------|-----------------------------------------------|--------------------------------------------|
| fijo       | tokenizador de multilingual-e5-small          | 256 tokens, overlap 32                     |
| oraciones  | spaCy es_core_news_sm + agrupación propia     | máx. 5 oraciones, overlap 1, tope 464 tok. |
| semantico  | spaCy + multilingual-e5-small (propio)        | umbral coseno 0.80 fijo, tope 464 tokens   |

Solo se fragmentan los documentos (fichas, políticas, manuales y guías). Productos, clientes y
compras son filas SQL: se consultan con SQL y entran al RAG como filtros.

Todos los tamaños se cuentan con el tokenizador del MISMO modelo que vectoriza, de modo que
"256 tokens" significa lo mismo que la ventana del modelo y ningún chunk se trunca.

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


def ventanas_de_tokens(texto: str, tokenizador, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Corta `texto` en ventanas de `chunk_size` tokens que se solapan `chunk_overlap` tokens.

    Usa los offsets del tokenizador para recortar el texto original, así el chunk guardado es
    legible (no se reconstruye a partir de los tokens).
    """
    if chunk_size <= chunk_overlap:
        raise ValueError("chunk_size debe ser mayor que chunk_overlap")
    codificado = tokenizador(texto, add_special_tokens=False, return_offsets_mapping=True,
                             truncation=False, verbose=False)
    offsets = codificado["offset_mapping"]
    n = len(offsets)
    if n == 0:
        return []
    paso = chunk_size - chunk_overlap
    chunks = []
    for inicio in range(0, n, paso):
        fin = min(inicio + chunk_size, n)
        trozo = texto[offsets[inicio][0]:offsets[fin - 1][1]].strip()
        if trozo:
            chunks.append(trozo)
        if fin >= n:
            break
    return chunks


def _acotar_oraciones(oraciones: list[str], modelos, max_tokens: int | None) -> list[str]:
    """Parte en ventanas de tokens cualquier oración que sola supere `max_tokens` (caso raro)."""
    if not max_tokens or modelos is None:
        return oraciones
    salida = []
    for o in oraciones:
        if modelos.contar_tokens(o) > max_tokens:
            salida.extend(ventanas_de_tokens(o, modelos.tokenizador, max_tokens - 2, 0))
        else:
            salida.append(o)
    return salida


# ------------------------------------------------------------------ 1. tamaño fijo
def chunk_fijo(texto: str, modelos, chunk_size: int = 256, chunk_overlap: int = 32) -> list[str]:
    """Ventanas de `chunk_size` tokens del tokenizador de e5 que se solapan `chunk_overlap`.

    No respeta oraciones ni palabras completas de forma deliberada: es la línea base.
    """
    return ventanas_de_tokens(texto, modelos.tokenizador, chunk_size, chunk_overlap)


# ------------------------------------------------------------------ 2. por oraciones
def ventanas_de_oraciones(oraciones: list[str], max_sentences: int = 5, overlap: int = 1,
                          n_tokens: list[int] | None = None, max_tokens: int | None = None) -> list[str]:
    """Agrupa oraciones completas en ventanas de hasta `max_sentences` que comparten `overlap`.

    Si se dan `n_tokens` y `max_tokens`, una ventana se cierra antes de pasar de `max_tokens`
    (así 5 oraciones muy largas no superan la ventana del modelo).
    """
    if max_sentences <= overlap:
        raise ValueError("max_sentences debe ser mayor que overlap")
    n = len(oraciones)
    chunks, inicio = [], 0
    while inicio < n:
        fin, tokens = inicio, 0
        while fin < n and fin - inicio < max_sentences:
            t = n_tokens[fin] if n_tokens else 0
            if max_tokens and n_tokens and fin > inicio and tokens + t > max_tokens:
                break
            tokens += t
            fin += 1
        chunks.append(" ".join(oraciones[inicio:fin]))
        if fin >= n:
            break
        inicio = max(fin - overlap, inicio + 1)
    return chunks


def chunk_oraciones(texto: str, modelos=None, max_sentences: int = 5, overlap: int = 1,
                    spacy_model: str = "es_core_news_sm", max_tokens: int | None = None) -> list[str]:
    oraciones = _acotar_oraciones(dividir_oraciones(texto, spacy_model), modelos, max_tokens)
    n_tokens = [modelos.contar_tokens(o) for o in oraciones] if (modelos is not None and max_tokens) else None
    return ventanas_de_oraciones(oraciones, max_sentences, overlap, n_tokens, max_tokens)


# ------------------------------------------------------------------ 3. semántico
def cortes_semanticos(vectores: np.ndarray, threshold: float, n_tokens: list[int] | None = None,
                      max_tokens: int | None = None, min_tokens: int = 0) -> tuple[list[int], np.ndarray]:
    """Decide dónde empieza cada chunk. Devuelve (índices de inicio, similitudes).

    Se recorren las oraciones en orden. Cada oración se compara (coseno) con el
    CENTROIDE del chunk que se está armando (promedio normalizado de sus oraciones):
      * si la similitud es >= threshold, la oración se agrega al chunk;
      * si es < threshold, cambió el tema y la oración abre un chunk nuevo.
    Protecciones:
      * si al agregar la oración el chunk superaría `max_tokens`, también se corta, para que
        ningún chunk pase de la ventana del modelo;
      * mientras el chunk tenga menos de `min_tokens` (por ejemplo, un título como
        "Cobertura.") no se corta: el título queda pegado a su primera oración.

    similitudes[i] = similitud de la oración i+1 con el chunk anterior.
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


def chunk_semantico(texto: str, modelos, threshold: float = 0.80, max_tokens: int | None = None,
                    min_tokens: int = 0, spacy_model: str = "es_core_news_sm", oraciones: list[str] | None = None,
                    vectores: np.ndarray | None = None) -> list[str]:
    """Agrupa oraciones consecutivas mientras sigan hablando de lo mismo.

    `modelos.embed_oraciones` vectoriza las oraciones con e5. Se pueden pasar `oraciones` y
    `vectores` ya calculados para no volver a vectorizar.
    """
    if oraciones is None:
        oraciones = _acotar_oraciones(dividir_oraciones(texto, spacy_model), modelos, max_tokens)
    if not oraciones:
        return []
    if vectores is None:
        vectores = modelos.embed_oraciones(oraciones)
    n_tokens = [modelos.contar_tokens(o) for o in oraciones] if (max_tokens or min_tokens) else None
    cortes, _ = cortes_semanticos(np.asarray(vectores), threshold, n_tokens, max_tokens, min_tokens)
    limites = cortes + [len(oraciones)]
    return [" ".join(oraciones[a:b]) for a, b in zip(limites[:-1], limites[1:])]


def preparar_oraciones(texto: str, modelos, spacy_model: str = "es_core_news_sm") -> tuple[list[str], np.ndarray]:
    """Oraciones (acotadas al tope de tokens) y sus vectores, para reutilizarlos."""
    tope = config.PARAMETROS_CHUNKING["semantico"].get("max_tokens")
    oraciones = _acotar_oraciones(dividir_oraciones(texto, spacy_model), modelos, tope)
    vectores = modelos.embed_oraciones(oraciones) if oraciones else np.zeros((0, config.DIM_TEXTO), dtype=np.float32)
    return oraciones, vectores


# ------------------------------------------------------------------ envoltorio
def generar_chunks(texto: str, estrategia: str, modelos, **params) -> tuple[list[str], dict]:
    """Aplica una estrategia con los parámetros de config y devuelve (chunks, parámetros usados).

    `params` solo admite `oraciones` y `vectores` precalculados (semántico): los parámetros
    del experimento no se cambian desde fuera.
    """
    if modelos is None:
        raise ValueError("Las tres estrategias necesitan el modelo (tokenizador o embeddings)")
    base = dict(config.PARAMETROS_CHUNKING[estrategia])
    precalculado = {k: params.pop(k) for k in ("oraciones", "vectores") if k in params}
    if params:
        raise ValueError(f"Parámetros no permitidos: {sorted(params)}. Los parámetros se fijan en config.py")
    comunes = {"tokenizador": config.MODELO_TEXTO}
    if estrategia == "fijo":
        chunks = chunk_fijo(texto, modelos, **base)
        usados = {**base, **comunes, "herramienta": "tokenizador del modelo (offsets)"}
    elif estrategia == "oraciones":
        chunks = chunk_oraciones(texto, modelos, **base)
        usados = {**base, **comunes, "herramienta": "spaCy + agrupación propia"}
    elif estrategia == "semantico":
        chunks = chunk_semantico(texto, modelos, **base, **precalculado)
        usados = {**base, **comunes, "comparacion": "oracion_vs_centroide",
                  "herramienta": "spaCy + sentence-transformers", "modelo": config.MODELO_TEXTO}
    else:
        raise ValueError(f"Estrategia desconocida: {estrategia}")
    return chunks, usados

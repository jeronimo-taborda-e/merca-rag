"""Experimento de chunking: comparar fijo, oraciones y semántico con las mismas preguntas.

Métricas de recuperación (por estrategia, sobre un conjunto de preguntas con el
documento que debería responderlas):
  * hit@1  : el primer chunk recuperado es del documento correcto
  * hit@k  : algún chunk del top k es del documento correcto
  * MRR@k  : promedio de 1 / posición del primer chunk correcto (0 si no aparece)
  * latencia de la búsqueda en PostgreSQL (ms)

Métricas de los chunks: cuántos hay, tamaño promedio y cuántos superan la longitud
que MiniLM puede leer (se truncan al vectorizar = contexto perdido).
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from . import busqueda, chunking, config
from .embeddings import texto_para_vectorizar

# (pregunta, codigo_doc que la responde)
PREGUNTAS_PRUEBA = [
    ("¿Cuánto cuesta el domicilio si mi pedido es de 50.000 pesos?", "POL_DOMICILIOS"),
    ("¿Hasta qué hora puedo pedir un domicilio un domingo?", "POL_DOMICILIOS"),
    ("¿Puedo cancelar un pedido que ya va en camino?", "POL_DOMICILIOS"),
    ("¿Cuántos días tengo para devolver un detergente?", "POL_DEVOLUCIONES"),
    ("Pagué con tarjeta de crédito, ¿cuánto tarda el reembolso?", "POL_DEVOLUCIONES"),
    ("¿Qué me dan si me llega un producto vencido?", "POL_DEVOLUCIONES"),
    ("¿A qué temperatura se deben guardar los lácteos y las carnes?", "MAN_CADENA_FRIO"),
    ("¿Por qué no se debe meter el banano en la nevera?", "MAN_CADENA_FRIO"),
    ("¿Cómo se calcula el stock mínimo de un producto?", "MAN_INVENTARIO"),
    ("¿Cada cuánto se hacen los conteos de inventario?", "MAN_INVENTARIO"),
    ("¿Qué licencia necesita un conductor de moto?", "MAN_CONDUCTORES"),
    ("¿Qué pasa si el cliente no está en casa cuando llega el domicilio?", "MAN_CONDUCTORES"),
    ("¿Qué medios de pago aceptan en la caja?", "MAN_CAJA"),
    ("¿Qué sede cierra más tarde?", "GUIA_PUNTOS_VENTA"),
    ("¿Cuál es la dirección del supermercado en Chipre?", "GUIA_PUNTOS_VENTA"),
    ("¿Cuántos gramos de café se usan por taza en cafetera de goteo?", "GUIA_CAFE_CALDAS"),
    ("¿Qué significan los sellos negros octagonales de los empaques?", "GUIA_ETIQUETADO"),
    ("¿La leche deslactosada sirve para alérgicos a la proteína de la leche?", "GUIA_ETIQUETADO"),
    ("¿Cómo se prepara la aguapanela con queso?", "GUIA_RECETAS"),
    ("¿Qué descuento tiene el café en noviembre?", "POL_PROMOCIONES"),
    ("¿Se pueden acumular dos promociones en el mismo producto?", "POL_PROMOCIONES"),
    ("¿Cuánto tiempo guardan mis datos de facturación?", "POL_DATOS_PERSONALES"),
    ("¿Cómo se conserva la pechuga de pollo?", "FICHA_PECHUGA_DE_POLLO"),
    ("fruta ácida de cáscara naranja para hacer jugo", "FICHA_LULO"),
    ("croquetas para gato que cuidan las vías urinarias", "FICHA_ALIMENTO_SECO_PARA_GATO"),
    ("pan redondo hecho con almidón de yuca y queso", "FICHA_PAN_DE_BONO"),
    ("¿Qué marcas de detergente líquido venden?", "FICHA_DETERGENTE_LIQUIDO"),
]


def _metricas(codigos_recuperados: list[str], esperado: str) -> dict:
    posicion = next((i for i, c in enumerate(codigos_recuperados, start=1) if c == esperado), None)
    return {"hit@1": float(posicion == 1), "hit@k": float(posicion is not None),
            "mrr": 1.0 / posicion if posicion else 0.0, "posicion": posicion}


# ------------------------------------------------------------------ sobre la base
def estadisticas_chunks(conn) -> pd.DataFrame:
    sql = """
        SELECT estrategia_chunking AS estrategia,
               count(*)                              AS chunks,
               count(DISTINCT id_doc)                AS documentos,
               round(avg(length(contenido_chunk)))   AS chars_promedio,
               round(avg(n_tokens))                  AS tokens_promedio,
               max(n_tokens)                         AS tokens_max,
               round(100.0 * avg((n_tokens > %s)::int), 1) AS pct_truncados
        FROM embeddings_texto
        GROUP BY estrategia_chunking
        ORDER BY estrategia_chunking
    """
    with conn.cursor() as cur:
        cur.execute(sql, (config.MAX_SEQ_TEXTO,))
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def evaluar_estrategias(conn, modelos, preguntas=PREGUNTAS_PRUEBA, k: int = 5,
                        estrategias=config.ESTRATEGIAS, guardar: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Corre cada pregunta contra cada estrategia en PostgreSQL. Devuelve (detalle, resumen)."""
    from .rag import guardar_consulta
    filas = []
    for estrategia in estrategias:
        for pregunta, esperado in preguntas:
            t0 = time.perf_counter()
            res = busqueda.buscar_texto_texto(conn, modelos, pregunta, estrategia=estrategia, k=k)
            ms = (time.perf_counter() - t0) * 1000
            m = _metricas(list(res["codigo_doc"]) if not res.empty else [], esperado)
            filas.append({"estrategia": estrategia, "pregunta": pregunta, "esperado": esperado,
                          "top1": res["codigo_doc"].iloc[0] if not res.empty else None,
                          "score_top1": float(res["score"].iloc[0]) if not res.empty else None,
                          "latencia_ms": round(ms, 1), **m})
            if guardar:
                guardar_consulta(conn, pregunta, "texto_texto", res, vector_texto=modelos.embed_texto([pregunta])[0],
                                 estrategia=estrategia, t_recuperacion_ms=round(ms, 2), t_total_ms=round(ms, 2))
    detalle = pd.DataFrame(filas)
    resumen = (detalle.groupby("estrategia")
               .agg(**{"hit@1": ("hit@1", "mean"), f"hit@{k}": ("hit@k", "mean"), f"MRR@{k}": ("mrr", "mean"),
                       "latencia_ms": ("latencia_ms", "median"), "score_top1": ("score_top1", "mean")})
               .round(3).reindex(list(estrategias)))
    return detalle, resumen


# ------------------------------------------------------------------ en memoria (sin tocar la base)
def experimento_umbral_semantico(documentos: list[dict], modelos, preguntas=PREGUNTAS_PRUEBA,
                                 thresholds=None, k: int = 5) -> pd.DataFrame:
    """Prueba varios umbrales del chunking semántico y mide la recuperación con NumPy.

    Permite elegir el umbral dentro del rango 0.60-0.70 de la Entrega 1 antes de
    guardar la estrategia 'semantico' en PostgreSQL.
    """
    thresholds = thresholds or config.PARAMETROS_CHUNKING["semantico"]["thresholds_experimento"]
    max_tokens = config.PARAMETROS_CHUNKING["semantico"].get("max_tokens")
    min_tokens = config.PARAMETROS_CHUNKING["semantico"].get("min_tokens", 0)
    # Oraciones y vectores por documento: se calculan UNA vez para todos los umbrales
    base = []
    for doc in documentos:
        oraciones = chunking.dividir_oraciones(doc["contenido_texto"])
        base.append((doc, oraciones, modelos.embed_texto(oraciones) if oraciones else None))
    qvecs = modelos.embed_texto([p for p, _ in preguntas])

    filas = []
    for th in thresholds:
        t0 = time.perf_counter()
        textos, codigos, tokens = [], [], []
        for doc, oraciones, vectores in base:
            if not oraciones:
                continue
            for ch in chunking.chunk_semantico("", modelos, threshold=th, max_tokens=max_tokens, min_tokens=min_tokens,
                                               oraciones=oraciones, vectores=vectores):
                t = texto_para_vectorizar(doc["titulo"], ch)
                textos.append(t)
                codigos.append(doc["codigo_doc"])
                tokens.append(modelos.contar_tokens(t))
        matriz = modelos.embed_texto(textos)
        sims = qvecs @ matriz.T
        metricas = []
        for (pregunta, esperado), fila in zip(preguntas, sims):
            top = np.argsort(-fila)[:k]
            metricas.append(_metricas([codigos[i] for i in top], esperado))
        tokens = np.array(tokens)
        filas.append({
            "threshold": th, "rango_entrega1": 0.60 <= th <= 0.70, "chunks": len(textos),
            "oraciones_por_chunk": round(sum(len(o) for _, o, _ in base) / max(len(textos), 1), 2),
            "tokens_promedio": round(float(tokens.mean()), 1), "tokens_max": int(tokens.max()),
            "pct_truncados": round(100 * float((tokens > config.MAX_SEQ_TEXTO).mean()), 1),
            "hit@1": round(np.mean([m["hit@1"] for m in metricas]), 3),
            f"hit@{k}": round(np.mean([m["hit@k"] for m in metricas]), 3),
            f"MRR@{k}": round(np.mean([m["mrr"] for m in metricas]), 3),
        })
        print(f"umbral {th:.2f}: {len(textos)} chunks en {time.perf_counter() - t0:.1f} s")
    return pd.DataFrame(filas)


def similitudes_consecutivas(documento: dict, modelos, threshold: float | None = None) -> tuple[list[str], np.ndarray, list[int]]:
    """Similitud de cada oración con el chunk que se venía armando y dónde se corta.

    Devuelve (oraciones, similitudes, cortes) para graficar las decisiones del chunking semántico.
    """
    params = config.PARAMETROS_CHUNKING["semantico"]
    threshold = params["threshold"] if threshold is None else threshold
    oraciones = chunking.dividir_oraciones(documento["contenido_texto"])
    vectores = modelos.embed_texto(oraciones)
    n_tokens = [modelos.contar_tokens(o) for o in oraciones]
    cortes, sims = chunking.cortes_semanticos(vectores, threshold, n_tokens, params.get("max_tokens"),
                                              params.get("min_tokens", 0))
    return oraciones, sims, cortes

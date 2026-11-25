"""Experimento de chunking: fijo vs oraciones vs semántico con las mismas preguntas.

Protocolo (Entrega 1, sección 7.2):
  1. El corpus se carga una sola vez y las tres estrategias fragmentan el mismo texto.
  2. El conjunto de evaluación (data/evaluacion/preguntas.csv: 30 preguntas con ground truth y
     documentos que las responden) se redactó ANTES de generar chunks y no se edita.
  3. Los parámetros están congelados en config.py (el umbral semántico es 0.80 fijo): aquí no se
     prueba ningún parámetro contra las métricas.
  4. Mismas condiciones: mismo modelo, top_k = 5, mismo LLM y prompt con temperatura 0.
  5. Cada pregunta se ejecuta con cada estrategia (30 x 3 = 90 corridas) y todo queda en la base:
     consulta (estrategia, respuesta, tiempos), resultado (chunks con posición y score) y evaluacion.
  6. Análisis por estrategia y por tipo de pregunta + prueba de Wilcoxon pareada.

Métricas
  * Recuperación (sin LLM, desde la vista v_resultados_experimento): hit@1, hit@k y MRR contra
    los documentos esperados de cada pregunta (pregunta_documento).
  * RAGAS (con un LLM juez): faithfulness, answer_relevancy y context_recall, calculadas con las
    definiciones de RAGAS (Es et al., 2023):
      - faithfulness     = afirmaciones de la respuesta respaldadas por el contexto / afirmaciones
      - answer_relevancy = coseno medio entre la pregunta y preguntas que el juez genera a partir
                           de la respuesta (0 si la respuesta es evasiva)
      - context_recall   = oraciones del ground truth atribuibles al contexto / oraciones del ground truth
"""
from __future__ import annotations

import csv
import itertools
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import chunking, config, rag


# ============================================================ conjunto de evaluación
def leer_conjunto(ruta: Path | None = None) -> list[dict]:
    ruta = Path(ruta or config.CONJUNTO_EVALUACION)
    with ruta.open(encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    for fila in filas:
        fila["documentos"] = [c.strip() for c in fila["documentos"].split(";") if c.strip()]
    return filas


def cargar_conjunto_evaluacion(conn, ruta: Path | None = None) -> pd.DataFrame:
    """Carga pregunta + pregunta_documento (idempotente). Los documentos deben estar cargados."""
    filas = leer_conjunto(ruta)
    autocommit_previo = conn.autocommit
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT codigo_doc, id_doc FROM documento")
            ids = dict(cur.fetchall())
            faltan = sorted({c for f in filas for c in f["documentos"] if c not in ids})
            if faltan:
                raise LookupError(f"Documentos del conjunto de evaluación que no están cargados: {faltan}")
            for f in filas:
                cur.execute(
                    """INSERT INTO pregunta (codigo_pregunta, texto_pregunta, ground_truth, tipo)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (codigo_pregunta) DO UPDATE SET texto_pregunta = EXCLUDED.texto_pregunta,
                           ground_truth = EXCLUDED.ground_truth, tipo = EXCLUDED.tipo
                       RETURNING id_pregunta""",
                    (f["codigo"], f["pregunta"], f["ground_truth"], f["tipo"]),
                )
                id_pregunta = cur.fetchone()[0]
                cur.execute("DELETE FROM pregunta_documento WHERE id_pregunta = %s", (id_pregunta,))
                cur.executemany("INSERT INTO pregunta_documento (id_pregunta, id_doc) VALUES (%s, %s)",
                                [(id_pregunta, ids[c]) for c in f["documentos"]])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = autocommit_previo
    return preguntas(conn)


def preguntas(conn) -> pd.DataFrame:
    sql = """
        SELECT p.id_pregunta, p.codigo_pregunta, p.tipo, p.texto_pregunta, p.ground_truth,
               string_agg(d.codigo_doc, ';' ORDER BY d.codigo_doc) AS documentos
        FROM pregunta p
        JOIN pregunta_documento pd ON pd.id_pregunta = p.id_pregunta
        JOIN documento d ON d.id_doc = pd.id_doc
        GROUP BY p.id_pregunta
        ORDER BY p.codigo_pregunta
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


# ============================================================ estadísticas de los chunks
def estadisticas_chunks(conn) -> pd.DataFrame:
    """Cuántos chunks produce cada estrategia y de qué tamaño (en tokens del modelo)."""
    sql = """
        SELECT estrategia_chunking AS estrategia,
               count(*)                              AS chunks,
               count(DISTINCT id_doc)                AS documentos,
               round(avg(length(contenido_chunk)))   AS chars_promedio,
               round(avg(n_tokens))                  AS tokens_promedio,
               min(n_tokens)                         AS tokens_min,
               max(n_tokens)                         AS tokens_max,
               count(*) FILTER (WHERE n_tokens > %s) AS truncados
        FROM embeddings_texto
        GROUP BY estrategia_chunking
        ORDER BY estrategia_chunking
    """
    with conn.cursor() as cur:
        cur.execute(sql, (config.MAX_SEQ_TEXTO,))
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def similitudes_consecutivas(documento: dict, modelos) -> tuple[list[str], np.ndarray, list[int]]:
    """Similitud de cada oración con el chunk que se venía armando y dónde se corta (umbral fijo).

    Solo para visualizar las decisiones del chunking semántico; no se usa para elegir parámetros.
    """
    params = config.PARAMETROS_CHUNKING["semantico"]
    oraciones, vectores = chunking.preparar_oraciones(documento["contenido_texto"], modelos)
    n_tokens = [modelos.contar_tokens(o) for o in oraciones]
    cortes, sims = chunking.cortes_semanticos(vectores, params["threshold"], n_tokens, params.get("max_tokens"),
                                              params.get("min_tokens", 0))
    return oraciones, sims, cortes


# ============================================================ ejecución del experimento
def ejecutar_experimento(conn, modelos, estrategias=config.ESTRATEGIAS, k: int = config.TOP_K,
                         rehacer: bool = False, cliente=None) -> pd.DataFrame:
    """Corre cada pregunta con cada estrategia y guarda las corridas (consulta + resultado).

    Si una corrida (pregunta, estrategia) ya existe se omite, salvo con rehacer=True, que la borra
    (con su evaluación) y la vuelve a ejecutar. Sin GROQ_API_KEY se guarda la recuperación pero no la
    respuesta: las métricas de recuperación se pueden calcular, las de RAGAS no.
    """
    ps = preguntas(conn)
    if ps.empty:
        raise LookupError("No hay preguntas: ejecute cargar_conjunto_evaluacion(conn) primero")
    hechas = omitidas = 0
    for estrategia in estrategias:
        for p in ps.itertuples():
            with conn.cursor() as cur:
                cur.execute("SELECT id_consulta FROM consulta WHERE id_pregunta = %s AND estrategia_chunking = %s",
                            (p.id_pregunta, estrategia))
                previa = cur.fetchone()
                if previa and not rehacer:
                    omitidas += 1
                    continue
                if previa:
                    cur.execute("DELETE FROM consulta WHERE id_consulta = %s", (previa[0],))
            rag.preguntar(conn, modelos, p.texto_pregunta, estrategia=estrategia, k=k,
                          id_pregunta=int(p.id_pregunta), cliente=cliente)
            hechas += 1
    print(f"Corridas nuevas: {hechas} | ya existentes: {omitidas}")
    return resultados_experimento(conn)


def resultados_experimento(conn) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM v_resultados_experimento ORDER BY codigo_pregunta, estrategia_chunking")
        df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    for c in ("reciprocal_rank", "tiempo_recuperacion_ms", "tiempo_total_ms",
              "faithfulness", "answer_relevancy", "context_recall"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


METRICAS = ["hit_1", "hit_k", "reciprocal_rank", "faithfulness", "answer_relevancy", "context_recall"]


def resumen(detalle: pd.DataFrame, por: str | list[str] = "estrategia_chunking") -> pd.DataFrame:
    """Promedio (y desviación) de cada métrica por estrategia (o por estrategia y tipo de pregunta)."""
    agregados = {}
    for m in METRICAS:
        agregados[f"{m}"] = (m, "mean")
    agregados["corridas"] = ("id_consulta", "count")
    agregados["evaluadas"] = ("faithfulness", "count")
    agregados["recuperacion_ms_mediana"] = ("tiempo_recuperacion_ms", "median")
    tabla = detalle.groupby(por).agg(**agregados).round(3).rename(columns={"reciprocal_rank": "MRR"})
    return tabla


def prueba_wilcoxon(detalle: pd.DataFrame, metrica: str = "context_recall", alfa: float = 0.05) -> pd.DataFrame:
    """Comparación pareada (misma pregunta) entre cada par de estrategias."""
    from scipy.stats import wilcoxon
    tabla = detalle.pivot_table(index="codigo_pregunta", columns="estrategia_chunking", values=metrica).dropna()
    filas = []
    for a, b in itertools.combinations(tabla.columns, 2):
        dif = tabla[a] - tabla[b]
        if (dif == 0).all():
            p = 1.0
        else:
            p = float(wilcoxon(tabla[a], tabla[b], zero_method="wilcox").pvalue)
        filas.append({"metrica": metrica, "estrategia_a": a, "estrategia_b": b, "n_pares": len(tabla),
                      "media_a": round(tabla[a].mean(), 3), "media_b": round(tabla[b].mean(), 3),
                      "p_valor": round(p, 4), "significativa": p < alfa})
    return pd.DataFrame(filas)


# ============================================================ métricas RAGAS (LLM juez)
def _espera_sugerida(error) -> float | None:
    """Segundos que pide esperar un 429: cabecera retry-after o "try again in 1h5m4.9s" del mensaje."""
    try:
        return float(error.response.headers["retry-after"])
    except (KeyError, ValueError):
        pass
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)(ms|s))?", str(error))
    if not m or not any(m.groups()):
        return None
    horas, minutos, segundos, unidad = m.groups()
    return (int(horas or 0) * 3600 + int(minutos or 0) * 60
            + float(segundos or 0) / (1000 if unidad == "ms" else 1))


class Juez:
    """LLM juez (OpenAI-compatible, por defecto Groq) que responde JSON con temperatura 0.

    Si el proveedor responde 429 (límite de tokens) espera lo que pida y reintenta, siempre que la
    espera no pase de espera_max_s; si es mayor (cuota diaria agotada) deja pasar RateLimitError.
    """

    def __init__(self, cliente=None, modelo: str = config.LLM_EVAL_MODEL, espera_max_s: float = 120):
        self.cliente = cliente or rag.cliente_llm()
        if self.cliente is None:
            raise RuntimeError("Las métricas RAGAS necesitan un LLM juez: configure GROQ_API_KEY en .env")
        self.modelo = modelo
        self.espera_max_s = espera_max_s

    @property
    def etiqueta(self) -> str:
        """Valor de evaluacion.modelo_eval: identifica con qué juez se calculó cada fila."""
        return f"RAGAS (definiciones) · juez {self.modelo}"

    def _completar(self, mensajes: list[dict]):
        from openai import RateLimitError
        while True:
            try:
                return self.cliente.chat.completions.create(model=self.modelo, temperature=0, messages=mensajes)
            except RateLimitError as error:
                espera = _espera_sugerida(error)
                if espera is None or espera > self.espera_max_s:
                    raise
                print(f"Límite de tokens: se espera {espera:.0f} s y se reintenta")
                time.sleep(espera + 1)

    def json(self, instruccion: str) -> dict:
        respuesta = self._completar([
            {"role": "system", "content": "Respondes únicamente con un objeto JSON válido, sin texto adicional."},
            {"role": "user", "content": instruccion},
        ])
        texto = respuesta.choices[0].message.content or "{}"
        coincidencia = re.search(r"\{.*\}", texto, flags=re.S)
        return json.loads(coincidencia.group(0) if coincidencia else "{}")


def _faithfulness(juez: Juez, pregunta: str, respuesta: str, contexto: str) -> float:
    afirmaciones = juez.json(
        "Descompón la RESPUESTA en afirmaciones atómicas e independientes (sin pronombres). "
        'Devuelve {"afirmaciones": ["...", "..."]}.\n\n'
        f"PREGUNTA: {pregunta}\nRESPUESTA: {respuesta}"
    ).get("afirmaciones", [])
    if not afirmaciones:
        return 1.0   # una respuesta sin afirmaciones ("no tengo esa información") no inventa nada
    veredictos = juez.json(
        "Para cada AFIRMACIÓN indica si se puede deducir directamente del CONTEXTO (1) o no (0). "
        'Devuelve {"veredictos": [1, 0, ...]} en el mismo orden.\n\n'
        f"CONTEXTO:\n{contexto}\n\nAFIRMACIONES:\n" + "\n".join(f"- {a}" for a in afirmaciones)
    ).get("veredictos", [])
    veredictos = [int(bool(v)) for v in veredictos][:len(afirmaciones)]
    return sum(veredictos) / len(afirmaciones)


def _answer_relevancy(juez: Juez, modelos, pregunta: str, respuesta: str, n: int = 3) -> float:
    salida = juez.json(
        f"Escribe {n} preguntas distintas que la RESPUESTA estaría respondiendo, y marca si la respuesta es "
        'evasiva o no se compromete (1) o no (0). Devuelve {"preguntas": ["..."], "evasiva": 0}.\n\n'
        f"RESPUESTA: {respuesta}"
    )
    generadas = [g for g in salida.get("preguntas", []) if isinstance(g, str) and g.strip()][:n]
    if not generadas or int(bool(salida.get("evasiva", 0))):
        return 0.0
    vectores = modelos.embed_consulta([pregunta] + generadas)
    similitudes = vectores[1:] @ vectores[0]
    return float(np.clip(similitudes.mean(), 0.0, 1.0))


def _context_recall(juez: Juez, ground_truth: str, contexto: str) -> float:
    salida = juez.json(
        "Divide la RESPUESTA DE REFERENCIA en oraciones y, para cada una, indica si se puede atribuir al "
        'CONTEXTO recuperado (1) o no (0). Devuelve {"oraciones": ["..."], "atribuibles": [1, 0, ...]}.\n\n'
        f"CONTEXTO:\n{contexto}\n\nRESPUESTA DE REFERENCIA: {ground_truth}"
    )
    atribuibles = [int(bool(v)) for v in salida.get("atribuibles", [])]
    return sum(atribuibles) / len(atribuibles) if atribuibles else 0.0


def evaluar_ragas(conn, modelos, juez: Juez | None = None, rehacer: bool = False) -> pd.DataFrame:
    """Calcula faithfulness, answer_relevancy y context_recall de cada corrida con respuesta.

    El contexto evaluado es exactamente el que recibió el LLM: los chunks guardados en resultado.

    Es reanudable: cada corrida se guarda al terminarla y la siguiente llamada solo procesa las que
    este juez no ha evaluado. Si se agota la cuota del LLM se detiene e informa cuántas faltan. Con
    otro juez se reevalúan todas las corridas (nunca se comparan métricas de jueces distintos).
    Se avanza pregunta por pregunta para que un resultado parcial tenga las tres estrategias.
    """
    from openai import RateLimitError
    juez = juez or Juez()
    sql = """
        SELECT c.id_consulta, p.texto_pregunta, p.ground_truth, c.respuesta_llm,
               string_agg(e.contenido_chunk, E'\\n\\n' ORDER BY r.posicion) AS contexto
        FROM consulta c
        JOIN pregunta p ON p.id_pregunta = c.id_pregunta
        JOIN resultado r ON r.id_consulta = c.id_consulta
        JOIN embeddings_texto e ON e.id_embedding = r.id_chunk
        WHERE c.respuesta_llm IS NOT NULL
          AND (%s OR NOT EXISTS (SELECT 1 FROM evaluacion ev WHERE ev.id_consulta = c.id_consulta
                                          AND ev.modelo_eval = %s))
        GROUP BY c.id_consulta, p.texto_pregunta, p.ground_truth, c.respuesta_llm
        ORDER BY min(c.id_pregunta), c.estrategia_chunking
    """
    with conn.cursor() as cur:
        cur.execute(sql, (rehacer, juez.etiqueta))
        pendientes = cur.fetchall()
    evaluadas = 0
    for id_consulta, pregunta, ground_truth, respuesta, contexto in pendientes:
        try:
            f = _faithfulness(juez, pregunta, respuesta, contexto)
            ar = _answer_relevancy(juez, modelos, pregunta, respuesta)
            cr = _context_recall(juez, ground_truth, contexto)
        except RateLimitError as error:
            espera = _espera_sugerida(error)
            print("Cuota del LLM agotada" + (f" (reintentar en {espera / 60:.0f} min)" if espera else "")
                  + f". Faltan {len(pendientes) - evaluadas} corridas: vuelva a ejecutar esta celda para "
                  "continuar. RESULTADOS PARCIALES: no sacar conclusiones todavía.")
            break
        rag.registrar_evaluacion(conn, id_consulta, f, ar, cr, juez.etiqueta)
        evaluadas += 1
    print(f"Corridas evaluadas: {evaluadas} de {len(pendientes)} pendientes")
    return resultados_experimento(conn)

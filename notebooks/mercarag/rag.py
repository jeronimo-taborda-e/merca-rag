"""Pipeline RAG: recuperar -> armar contexto -> generar -> guardar trazabilidad.

El LLM no consulta la base: primero se recupera evidencia con SQL + vectores, se arma
un texto de contexto y ese texto se envía al LLM (Groq, API compatible con OpenAI).
"""
from __future__ import annotations

import time

import pandas as pd
from psycopg2.extras import execute_values

from . import busqueda, config

SYSTEM_PROMPT = (
    "Eres el asistente de MercaRAG, un supermercado de Manizales. Responde en español, "
    "de forma breve y precisa, usando SOLO la información del contexto. Si el contexto no "
    "contiene la respuesta, di que no tienes esa información. Cita entre corchetes el código "
    "del documento que usaste, por ejemplo [POL_DOMICILIOS]."
)


# ------------------------------------------------------------------ contexto
def construir_contexto_texto(resultados: pd.DataFrame, max_chars: int = config.MAX_CHARS_CONTEXTO) -> str:
    bloques, total = [], 0
    for i, fila in enumerate(resultados.itertuples(), start=1):
        bloque = (f"[{i}] Documento: {fila.codigo_doc} - {fila.titulo} (score {fila.score:.3f})\n"
                  f"{fila.contenido_chunk}")
        if total + len(bloque) > max_chars:
            break
        bloques.append(bloque)
        total += len(bloque)
    return "\n\n".join(bloques)


def construir_contexto_imagen(resultados: pd.DataFrame) -> str:
    """El LLM solo lee texto: cada foto se describe con sus metadatos relacionales."""
    if resultados is None or resultados.empty:
        return ""
    lineas = [f"- Foto {f.codigo_img}: {f.descripcion or ''}; producto: {f.producto or 'sin producto'}; "
              f"categoría: {f.categoria or '-'}; archivo {f.ruta_archivo} (score {f.score:.3f})"
              for f in resultados.itertuples()]
    return "Imágenes relacionadas:\n" + "\n".join(lineas)


# ------------------------------------------------------------------ LLM
def cliente_llm():
    """Cliente OpenAI-compatible (Groq) o None si no hay GROQ_API_KEY."""
    if not config.GROQ_API_KEY:
        return None
    from openai import OpenAI
    return OpenAI(api_key=config.GROQ_API_KEY, base_url=config.LLM_BASE_URL)


def generar_respuesta(pregunta: str, contexto: str, modelo: str = config.LLM_MODEL, cliente=None) -> str | None:
    """Devuelve la respuesta del LLM o None si no hay cliente (sin GROQ_API_KEY)."""
    cliente = cliente or cliente_llm()
    if cliente is None:
        return None
    respuesta = cliente.chat.completions.create(
        model=modelo,
        temperature=config.LLM_TEMPERATURA,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Contexto:\n{contexto}\n\nPregunta: {pregunta}"},
        ],
    )
    return respuesta.choices[0].message.content


# ------------------------------------------------------------------ trazabilidad
def id_usuario(conn, email: str = config.EMAIL_USUARIO_NOTEBOOK) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT id_usuario FROM usuario WHERE email = %s", (email,))
        fila = cur.fetchone()
        if fila is None:
            raise LookupError(f"No existe el usuario {email}; ¿se cargó sql/02_datos_dominio.sql?")
        return fila[0]


def _score(valor) -> float:
    """Similitud coseno redondeada y acotada a [-1, 1] (el redondeo flotante puede dar 1.0000001)."""
    return max(-1.0, min(1.0, round(float(valor), 6)))


def guardar_consulta(conn, tipo_consulta: str, pregunta: str | None = None, id_pregunta: int | None = None,
                     resultados_texto: pd.DataFrame | None = None, resultados_imagen: pd.DataFrame | None = None,
                     vector_texto=None, vector_clip=None, estrategia: str | None = None, top_k: int = config.TOP_K,
                     respuesta: str | None = None, modelo_llm: str | None = None,
                     t_recuperacion_ms: float | None = None, t_total_ms: float | None = None,
                     ruta_imagen: str | None = None, email: str = config.EMAIL_USUARIO_NOTEBOOK) -> int:
    """Guarda en una transacción la consulta, sus vectores y cada resultado con su posición.

    * Consulta del experimento: se pasa `id_pregunta` (el texto y el ground truth están en pregunta).
    * Consulta libre: se pasa `pregunta` (texto).  * Consulta con foto: se pasa `ruta_imagen`.
    Los resultados de texto guardan el CHUNK (id_chunk) y los de imagen la foto (id_img).
    """
    autocommit_previo = conn.autocommit
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO consulta (id_usuario, id_pregunta, texto_pregunta, ruta_imagen_consulta, tipo_consulta,
                                         estrategia_chunking, top_k, respuesta_llm, modelo_llm,
                                         tiempo_recuperacion_ms, tiempo_total_ms)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id_consulta""",
                (id_usuario(conn, email), id_pregunta, None if id_pregunta else pregunta, ruta_imagen,
                 tipo_consulta, estrategia, top_k, respuesta, modelo_llm if respuesta else None,
                 t_recuperacion_ms, t_total_ms),
            )
            id_consulta = cur.fetchone()[0]
            if vector_texto is not None or vector_clip is not None:
                cur.execute(
                    """INSERT INTO query_embeddings (id_consulta, vector_texto, modelo_texto, vector_clip, modelo_clip)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (id_consulta, vector_texto, config.MODELO_TEXTO if vector_texto is not None else None,
                     vector_clip, (config.MODELO_CLIP_IMAGEN if ruta_imagen else config.MODELO_CLIP_TEXTO)
                     if vector_clip is not None else None),
                )
            filas, posicion = [], 1
            for f in (resultados_texto.itertuples() if resultados_texto is not None else []):
                filas.append((id_consulta, int(f.id_embedding), None, posicion, _score(f.score)))
                posicion += 1
            for f in (resultados_imagen.itertuples() if resultados_imagen is not None else []):
                filas.append((id_consulta, None, int(f.id_img), posicion, _score(f.score)))
                posicion += 1
            if filas:
                execute_values(cur, """INSERT INTO resultado (id_consulta, id_chunk, id_img, posicion, score_similitud)
                                       VALUES %s""", filas)
        conn.commit()
        return id_consulta
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = autocommit_previo


def registrar_evaluacion(conn, id_consulta: int, faithfulness: float, answer_relevancy: float,
                         context_recall: float, modelo_eval: str) -> None:
    """Métricas RAGAS de una corrida del experimento (tabla evaluacion, 1:1 con consulta)."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO evaluacion (id_consulta, faithfulness, answer_relevancy, context_recall, modelo_eval)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (id_consulta) DO UPDATE SET faithfulness = EXCLUDED.faithfulness,
                   answer_relevancy = EXCLUDED.answer_relevancy, context_recall = EXCLUDED.context_recall,
                   modelo_eval = EXCLUDED.modelo_eval, fecha = CURRENT_TIMESTAMP""",
            (id_consulta, round(faithfulness, 3), round(answer_relevancy, 3), round(context_recall, 3), modelo_eval),
        )
    if not conn.autocommit:
        conn.commit()


# ------------------------------------------------------------------ pipeline completo
def preguntar(conn, modelos, pregunta: str, estrategia: str = "semantico", k: int = config.TOP_K,
              k_imagenes: int = 3, guardar: bool = True, id_pregunta: int | None = None, cliente=None) -> dict:
    """RF-06: respuesta en lenguaje natural con contexto recuperado de los documentos.

    Con `id_pregunta` la consulta queda registrada como corrida del experimento de chunking
    (sin imágenes: el experimento compara solo la recuperación de chunks).
    """
    if id_pregunta is not None:
        k_imagenes = 0
    t0 = time.perf_counter()
    res_texto = busqueda.buscar_texto_texto(conn, modelos, pregunta, estrategia=estrategia, k=k)
    res_img = busqueda.buscar_texto_imagen(conn, modelos, pregunta, k=k_imagenes) if k_imagenes else None
    t_recuperacion = (time.perf_counter() - t0) * 1000

    contexto = construir_contexto_texto(res_texto)
    if res_img is not None and not res_img.empty:
        contexto += "\n\n" + construir_contexto_imagen(res_img)
    respuesta = generar_respuesta(pregunta, contexto, cliente=cliente)
    t_total = (time.perf_counter() - t0) * 1000

    id_consulta = None
    if guardar:
        id_consulta = guardar_consulta(
            conn, "rag", pregunta=pregunta, id_pregunta=id_pregunta,
            resultados_texto=res_texto, resultados_imagen=res_img,
            vector_texto=modelos.embed_consulta([pregunta])[0],
            vector_clip=modelos.embed_texto_clip([pregunta])[0] if k_imagenes else None,
            estrategia=estrategia, top_k=k, respuesta=respuesta, modelo_llm=config.LLM_MODEL,
            t_recuperacion_ms=round(t_recuperacion, 2), t_total_ms=round(t_total, 2),
        )
    return {"id_consulta": id_consulta, "pregunta": pregunta, "respuesta": respuesta, "contexto": contexto,
            "contextos": list(res_texto["contenido_chunk"]) if not res_texto.empty else [],
            "resultados_texto": res_texto, "resultados_imagen": res_img,
            "tiempo_recuperacion_ms": round(t_recuperacion, 1), "tiempo_total_ms": round(t_total, 1)}


def historial(conn, n: int = 10) -> pd.DataFrame:
    """Reconstruye las últimas consultas con sus resultados (JOIN de la trazabilidad)."""
    sql = """
        SELECT c.id_consulta, c.fecha, u.email, c.tipo_consulta, c.estrategia_chunking AS estrategia,
               left(COALESCE(p.texto_pregunta, c.texto_pregunta, c.ruta_imagen_consulta), 60) AS pregunta,
               r.posicion, COALESCE(d.codigo_doc || ' #' || e.chunk_id, i.codigo_img) AS recurso,
               r.score_similitud AS score, c.tiempo_recuperacion_ms, c.tiempo_total_ms,
               left(c.respuesta_llm, 80) AS respuesta
        FROM (SELECT * FROM consulta ORDER BY id_consulta DESC LIMIT %s) c
        JOIN usuario u ON u.id_usuario = c.id_usuario
        LEFT JOIN pregunta p ON p.id_pregunta = c.id_pregunta
        LEFT JOIN resultado r ON r.id_consulta = c.id_consulta
        LEFT JOIN embeddings_texto e ON e.id_embedding = r.id_chunk
        LEFT JOIN documento d ON d.id_doc = e.id_doc
        LEFT JOIN imagen i ON i.id_img = r.id_img
        ORDER BY c.id_consulta DESC, r.posicion
    """
    with conn.cursor() as cur:
        cur.execute(sql, (n,))
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])

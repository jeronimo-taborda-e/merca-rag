"""Carga transaccional e idempotente de documentos, chunks, imágenes y vectores.

Patrón del laboratorio:
  * INSERT ... ON CONFLICT (codigo_doc / sha256) DO UPDATE ... RETURNING id  -> repetible
  * todo dentro de una transacción: si algo falla, ROLLBACK y la base queda igual
  * se vectoriza en lote (más rápido) y se inserta con execute_values
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path

import numpy as np
from psycopg2.extras import execute_values

from . import chunking, config
from .embeddings import abrir_imagen, texto_para_vectorizar

EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".webp"}


# ======================================================================= documentos
def _id_producto(cur, codigo_barras: str | None):
    if not codigo_barras:
        return None
    cur.execute("SELECT id_producto FROM producto WHERE codigo_barras = %s", (codigo_barras,))
    fila = cur.fetchone()
    return fila[0] if fila else None


def _upsert_documento(cur, doc: dict, id_producto) -> int:
    cur.execute(
        """
        INSERT INTO documento (id_producto, codigo_doc, tipo, titulo, idioma, fecha, fuente, contenido_texto)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (codigo_doc) DO UPDATE SET
            id_producto = EXCLUDED.id_producto, tipo = EXCLUDED.tipo, titulo = EXCLUDED.titulo,
            idioma = EXCLUDED.idioma, fecha = EXCLUDED.fecha, fuente = EXCLUDED.fuente,
            contenido_texto = EXCLUDED.contenido_texto
        RETURNING id_doc
        """,
        (id_producto, doc["codigo_doc"], doc["tipo"], doc["titulo"], doc["idioma"], doc["fecha"],
         doc["fuente"], doc["contenido_texto"]),
    )
    return cur.fetchone()[0]


def preparar_chunks(documentos: list[dict], modelos, estrategias=config.ESTRATEGIAS,
                    params: dict | None = None) -> list[dict]:
    """Genera los chunks de cada documento con cada estrategia (sin tocar la base)."""
    params = params or {}
    filas = []
    for doc in documentos:
        oraciones = vectores_oraciones = None
        for estrategia in estrategias:
            extra = dict(params.get(estrategia, {}))
            if estrategia == "semantico":
                # Las oraciones y sus vectores se calculan una vez por documento
                if oraciones is None:
                    oraciones = chunking.dividir_oraciones(doc["contenido_texto"])
                    vectores_oraciones = modelos.embed_texto(oraciones) if oraciones else np.zeros((0, config.DIM_TEXTO))
                extra.update(oraciones=oraciones, vectores=vectores_oraciones)
            chunks, usados = chunking.generar_chunks(doc["contenido_texto"], estrategia, modelos, **extra)
            for i, texto in enumerate(chunks):
                filas.append({
                    "codigo_doc": doc["codigo_doc"], "titulo": doc["titulo"], "estrategia": estrategia,
                    "chunk_id": i, "contenido": texto, "parametros": usados,
                })
    return filas


def cargar_documentos(conn, documentos: list[dict], modelos, estrategias=config.ESTRATEGIAS,
                      params: dict | None = None, con_clip: bool = True) -> dict:
    """Inserta documentos + chunks + vectores MiniLM (384) y CLIP texto (512)."""
    t0 = time.perf_counter()
    filas = preparar_chunks(documentos, modelos, estrategias, params)

    a_vectorizar = [texto_para_vectorizar(f["titulo"], f["contenido"]) for f in filas]
    vec_minilm = modelos.embed_texto(a_vectorizar) if filas else []
    vec_clip = modelos.embed_texto_clip(a_vectorizar) if (filas and con_clip) else None
    for f, texto in zip(filas, a_vectorizar):
        f["n_tokens"] = modelos.contar_tokens(texto)

    autocommit_previo = conn.autocommit
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            ids_doc = {}
            for doc in documentos:
                id_producto = _id_producto(cur, doc.get("codigo_barras"))
                ids_doc[doc["codigo_doc"]] = _upsert_documento(cur, doc, id_producto)
                # Recarga: se borran los chunks previos de las estrategias que se van a regenerar
                # (embeddings_texto_clip cae por CASCADE; resultado.id_embedding_texto queda NULL)
                cur.execute("DELETE FROM embeddings_texto WHERE id_doc = %s AND estrategia_chunking = ANY(%s)",
                            (ids_doc[doc["codigo_doc"]], list(estrategias)))

            if filas:
                valores = [
                    (ids_doc[f["codigo_doc"]], f["chunk_id"], f["estrategia"], f["contenido"], f["n_tokens"],
                     json.dumps(f["parametros"], ensure_ascii=False), vec_minilm[i], config.MODELO_TEXTO)
                    for i, f in enumerate(filas)
                ]
                ids_chunk = execute_values(
                    cur,
                    """INSERT INTO embeddings_texto (id_doc, chunk_id, estrategia_chunking, contenido_chunk,
                                                     n_tokens, parametros, vector_embedding, modelo)
                       VALUES %s RETURNING id_embedding""",
                    valores, page_size=200, fetch=True,
                )
                if vec_clip is not None:
                    execute_values(
                        cur,
                        "INSERT INTO embeddings_texto_clip (id_embedding, vector_embedding, modelo) VALUES %s",
                        [(ids_chunk[i][0], vec_clip[i], config.MODELO_CLIP_TEXTO) for i in range(len(filas))],
                        page_size=200,
                    )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = autocommit_previo

    por_estrategia = {e: sum(1 for f in filas if f["estrategia"] == e) for e in estrategias}
    return {"documentos": len(documentos), "chunks": len(filas), "por_estrategia": por_estrategia,
            "segundos": round(time.perf_counter() - t0, 2)}


# ======================================================================= imágenes
def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def catalogo_imagenes(directorio: Path | None = None) -> list[dict]:
    """Recorre data/imagenes/<carpeta>/ y arma el catálogo de fotos.

    Convención: el nombre de la carpeta es el producto base de la ficha, por ejemplo
    data/imagenes/aguacate_hass/  ->  documento FICHA_AGUACATE_HASS (y su producto).
    Si existe data/imagenes/manifest.csv (archivo, codigo_doc, codigo_barras,
    descripcion, etiquetas separadas por ';'), sus valores tienen prioridad.
    """
    directorio = Path(directorio or config.IMAGENES_DIR)
    manifest = {}
    ruta_manifest = directorio / "manifest.csv"
    if ruta_manifest.exists():
        with ruta_manifest.open(encoding="utf-8") as f:
            manifest = {fila["archivo"]: fila for fila in csv.DictReader(f)}

    catalogo = []
    for ruta in sorted(directorio.rglob("*")):
        if ruta.suffix.lower() not in EXTENSIONES_IMAGEN or ruta.name.startswith("."):
            continue
        rel_imagenes = ruta.relative_to(directorio).as_posix()
        carpeta = ruta.parent.name if ruta.parent != directorio else "sin_categoria"
        meta = manifest.get(rel_imagenes) or manifest.get(ruta.name) or {}
        sha = _sha256(ruta)
        with abrir_imagen(ruta) as im:
            ancho, alto = im.size
        etiquetas = [e.strip() for e in (meta.get("etiquetas") or "").split(";") if e.strip()]
        etiquetas = etiquetas or [carpeta.replace("_", " ")]
        catalogo.append({
            "codigo_img": f"IMG_{_slug(carpeta).upper()[:20]}_{sha[:8]}",
            "ruta": ruta,
            "ruta_archivo": ruta.relative_to(directorio.parent).as_posix(),  # relativa a data/
            "sha256": sha, "ancho": ancho, "alto": alto,
            "codigo_doc": meta.get("codigo_doc") or f"FICHA_{_slug(carpeta).upper()}",
            "codigo_barras": meta.get("codigo_barras") or None,
            "descripcion": meta.get("descripcion") or carpeta.replace("_", " "),
            "etiquetas": etiquetas,
        })
    return catalogo


def cargar_imagenes(conn, catalogo: list[dict], modelos, lote: int = 16) -> dict:
    """Inserta imagen + etiquetas + vector CLIP de los píxeles, en una transacción."""
    t0 = time.perf_counter()
    autocommit_previo = conn.autocommit
    conn.autocommit = False
    insertadas = 0
    try:
        with conn.cursor() as cur:
            for inicio in range(0, len(catalogo), lote):
                grupo = catalogo[inicio:inicio + lote]
                vectores = modelos.embed_imagenes([abrir_imagen(c["ruta"]) for c in grupo])
                for item, vector in zip(grupo, vectores):
                    cur.execute("SELECT id_doc, id_producto FROM documento WHERE codigo_doc = %s", (item["codigo_doc"],))
                    doc = cur.fetchone() or (None, None)
                    id_producto = _id_producto(cur, item["codigo_barras"]) or doc[1]
                    cur.execute(
                        """
                        INSERT INTO imagen (id_doc, id_producto, codigo_img, ruta_archivo, sha256, ancho, alto, descripcion)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (sha256) DO UPDATE SET
                            id_doc = EXCLUDED.id_doc, id_producto = EXCLUDED.id_producto,
                            ruta_archivo = EXCLUDED.ruta_archivo, descripcion = EXCLUDED.descripcion
                        RETURNING id_img
                        """,
                        (doc[0], id_producto, item["codigo_img"], item["ruta_archivo"], item["sha256"],
                         item["ancho"], item["alto"], item["descripcion"]),
                    )
                    id_img = cur.fetchone()[0]
                    execute_values(cur, "INSERT INTO imagen_etiqueta (id_img, etiqueta) VALUES %s ON CONFLICT DO NOTHING",
                                   [(id_img, e) for e in item["etiquetas"]])
                    cur.execute(
                        """
                        INSERT INTO embeddings_imagen (id_img, vector_embedding, modelo) VALUES (%s, %s, %s)
                        ON CONFLICT (id_img, modelo) DO UPDATE SET vector_embedding = EXCLUDED.vector_embedding
                        """,
                        (id_img, vector, config.MODELO_CLIP_IMAGEN),
                    )
                    insertadas += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = autocommit_previo
    return {"imagenes": insertadas, "segundos": round(time.perf_counter() - t0, 2)}


# ======================================================================= integridad
def verificar_integridad(conn) -> dict:
    """Cuenta filas y comprueba que ningún chunk ni imagen haya quedado sin vector."""
    consultas = {
        "documentos": "SELECT count(*) FROM documento",
        "chunks": "SELECT count(*) FROM embeddings_texto",
        "imagenes": "SELECT count(*) FROM imagen",
        "docs_sin_chunks": """SELECT count(*) FROM documento d
                              WHERE NOT EXISTS (SELECT 1 FROM embeddings_texto e WHERE e.id_doc = d.id_doc)""",
        "chunks_sin_vector_clip": """SELECT count(*) FROM embeddings_texto e
                                     LEFT JOIN embeddings_texto_clip c ON c.id_embedding = e.id_embedding
                                     WHERE c.id_embedding IS NULL""",
        "imagenes_sin_vector": """SELECT count(*) FROM imagen i
                                  LEFT JOIN embeddings_imagen e ON e.id_img = i.id_img
                                  WHERE e.id_embedding IS NULL""",
    }
    with conn.cursor() as cur:
        resultado = {}
        for nombre, sql in consultas.items():
            cur.execute(sql)
            resultado[nombre] = cur.fetchone()[0]
    return resultado

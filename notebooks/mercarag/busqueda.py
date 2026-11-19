"""Rutas de búsqueda del laboratorio aplicadas a MercaRAG.

Todas siguen el mismo patrón:
  1. vectorizar la consulta con el modelo correcto (mismo espacio que lo guardado)
  2. un SQL que une la tabla de embeddings con las tablas relacionales
  3. ORDER BY vector <=> consulta LIMIT k   (distancia coseno; score = 1 - distancia)

| Función                   | Vectoriza con     | Busca en                | Requerimiento |
|---------------------------|-------------------|-------------------------|---------------|
| buscar_texto_texto        | MiniLM (384)      | embeddings_texto        | RF-06         |
| buscar_texto_imagen       | CLIP texto (512)  | embeddings_imagen       | RF-09         |
| buscar_imagen_imagen      | CLIP imagen (512) | embeddings_imagen       |               |
| buscar_imagen_texto       | CLIP imagen (512) | embeddings_texto_clip   |               |
| productos_similares       | MiniLM (384)      | fichas de producto      | RF-04         |
| buscar_productos_hibrida  | MiniLM (384)      | fichas + inventario     | RF-05         |
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .db import consultar
from .embeddings import abrir_imagen


def _df(filas) -> pd.DataFrame:
    df = pd.DataFrame(filas)
    if "score" in df:
        df["score"] = df["score"].astype(float).round(4)
    return df


# ------------------------------------------------------------------ texto -> texto
def buscar_texto_texto(conn, modelos, pregunta: str, estrategia: str = "semantico", k: int = 5,
                       tipo: str | None = None, id_producto: int | None = None) -> pd.DataFrame:
    """Chunks más parecidos a la pregunta, con filtros relacionales opcionales."""
    qvec = modelos.embed_texto([pregunta])[0]
    sql = """
        SELECT e.id_embedding, d.id_doc, d.codigo_doc, d.titulo, d.tipo, e.chunk_id,
               e.estrategia_chunking AS estrategia, e.contenido_chunk,
               1 - (e.vector_embedding <=> %s) AS score
        FROM embeddings_texto e
        JOIN documento d ON d.id_doc = e.id_doc
        WHERE e.estrategia_chunking = %s
          AND (%s::text IS NULL OR d.tipo = %s)
          AND (%s::int  IS NULL OR d.id_producto = %s)
        ORDER BY e.vector_embedding <=> %s
        LIMIT %s
    """
    return _df(consultar(conn, sql, (qvec, estrategia, tipo, tipo, id_producto, id_producto, qvec, k)))


# ------------------------------------------------------------------ texto -> imagen
def buscar_texto_imagen(conn, modelos, texto: str, k: int = 5, categoria: str | None = None) -> pd.DataFrame:
    """RF-09: fotos del catálogo que corresponden a una descripción escrita."""
    qvec = modelos.embed_texto_clip([texto])[0]
    sql = """
        SELECT i.id_img, i.codigo_img, i.ruta_archivo, i.descripcion, p.nombre AS producto,
               c.nombre AS categoria, 1 - (e.vector_embedding <=> %s) AS score
        FROM embeddings_imagen e
        JOIN imagen i ON i.id_img = e.id_img
        LEFT JOIN producto p  ON p.id_producto = i.id_producto
        LEFT JOIN categoria c ON c.id_categoria = p.id_categoria
        WHERE (%s::text IS NULL OR c.nombre = %s)
        ORDER BY e.vector_embedding <=> %s
        LIMIT %s
    """
    return _df(consultar(conn, sql, (qvec, categoria, categoria, qvec, k)))


# ------------------------------------------------------------------ imagen -> imagen
def buscar_imagen_imagen(conn, modelos, ruta: str | Path, k: int = 5) -> pd.DataFrame:
    qvec = modelos.embed_imagenes([abrir_imagen(ruta)])[0]
    sql = """
        SELECT i.id_img, i.codigo_img, i.ruta_archivo, p.nombre AS producto,
               1 - (e.vector_embedding <=> %s) AS score
        FROM embeddings_imagen e
        JOIN imagen i ON i.id_img = e.id_img
        LEFT JOIN producto p ON p.id_producto = i.id_producto
        ORDER BY e.vector_embedding <=> %s
        LIMIT %s
    """
    return _df(consultar(conn, sql, (qvec, qvec, k)))


# ------------------------------------------------------------------ imagen -> texto
def buscar_imagen_texto(conn, modelos, ruta: str | Path, k: int = 5, estrategia: str = "semantico") -> pd.DataFrame:
    """Una foto encuentra los chunks que hablan de ella (ambos en el espacio CLIP)."""
    qvec = modelos.embed_imagenes([abrir_imagen(ruta)])[0]
    sql = """
        SELECT t.id_embedding, d.codigo_doc, d.titulo, t.contenido_chunk,
               1 - (c.vector_embedding <=> %s) AS score
        FROM embeddings_texto_clip c
        JOIN embeddings_texto t ON t.id_embedding = c.id_embedding
        JOIN documento d ON d.id_doc = t.id_doc
        WHERE t.estrategia_chunking = %s
        ORDER BY c.vector_embedding <=> %s
        LIMIT %s
    """
    return _df(consultar(conn, sql, (qvec, estrategia, qvec, k)))


# ------------------------------------------------------------------ RF-04 / RF-05
_SQL_FICHAS_CERCANAS = """
    -- Fichas de producto más cercanas a la descripción (mejor chunk de cada ficha)
    WITH fichas AS (
        SELECT d.id_doc, d.titulo, split_part(d.titulo, ' - ', 2) AS producto_base,
               MIN(e.vector_embedding <=> %(q)s) AS distancia
        FROM embeddings_texto e
        JOIN documento d ON d.id_doc = e.id_doc
        WHERE e.estrategia_chunking = %(estrategia)s AND d.tipo = 'ficha'
        GROUP BY d.id_doc, d.titulo
        ORDER BY distancia
        LIMIT %(n_fichas)s
    )
"""


def productos_similares(conn, modelos, descripcion: str, k: int = 10, estrategia: str = "semantico") -> pd.DataFrame:
    """RF-04: productos (todas las marcas y presentaciones) parecidos a una descripción."""
    sql = _SQL_FICHAS_CERCANAS + """
        SELECT f.producto_base, p.nombre AS producto, m.nombre AS marca, c.nombre AS categoria,
               p.precio, 1 - f.distancia AS score
        FROM fichas f
        JOIN producto p  ON p.nombre LIKE f.producto_base || ' %%'
        JOIN marca m     ON m.id_marca = p.id_marca
        JOIN categoria c ON c.id_categoria = p.id_categoria
        ORDER BY f.distancia, p.precio
        LIMIT %(k)s
    """
    q = modelos.embed_texto([descripcion])[0]
    return _df(consultar(conn, sql, {"q": q, "estrategia": estrategia, "n_fichas": 5, "k": k}))


def buscar_productos_hibrida(conn, modelos, descripcion: str, sede: str | None = None,
                             precio_max: float | None = None, k: int = 10,
                             estrategia: str = "semantico", solo_promocion: bool = False) -> pd.DataFrame:
    """RF-05: búsqueda híbrida = similitud semántica + filtros SQL clásicos.

    Productos descritos en lenguaje natural, disponibles (stock > 0) en una sede y
    por debajo de un precio; opcionalmente solo los que tienen promoción vigente.
    """
    sql = _SQL_FICHAS_CERCANAS + """
        SELECT p.nombre AS producto, m.nombre AS marca, p.precio, pv.nombre AS sede,
               i.stock, pr.nombre AS promocion, 1 - f.distancia AS score
        FROM fichas f
        JOIN producto p     ON p.nombre LIKE f.producto_base || ' %%'
        JOIN marca m        ON m.id_marca = p.id_marca
        JOIN inventario i   ON i.id_producto = p.id_producto AND i.stock > 0
        JOIN punto_venta pv ON pv.id_punto_venta = i.id_punto_venta
        LEFT JOIN LATERAL (
            SELECT pm.nombre FROM promocion_producto pp
            JOIN promocion pm ON pm.id_promocion = pp.id_promocion
            WHERE pp.id_producto = p.id_producto
              AND CURRENT_DATE BETWEEN pm.fecha_inicio AND pm.fecha_fin
            ORDER BY pm.valor DESC LIMIT 1
        ) pr ON TRUE
        WHERE (%(sede)s::text IS NULL OR pv.nombre = %(sede)s)
          AND (%(precio_max)s::numeric IS NULL OR p.precio <= %(precio_max)s)
          AND (NOT %(solo_promo)s OR pr.nombre IS NOT NULL)
        ORDER BY f.distancia, p.precio
        LIMIT %(k)s
    """
    q = modelos.embed_texto([descripcion])[0]
    return _df(consultar(conn, sql, {"q": q, "estrategia": estrategia, "n_fichas": 5, "sede": sede,
                                     "precio_max": precio_max, "solo_promo": solo_promocion, "k": k}))

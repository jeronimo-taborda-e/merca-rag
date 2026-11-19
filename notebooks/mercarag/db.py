"""Conexión a PostgreSQL + pgvector."""
from __future__ import annotations

import psycopg2
from pgvector.psycopg2 import register_vector

from . import config


def get_connection(autocommit: bool = True):
    """Abre una conexión y registra el tipo vector.

    autocommit=True evita que un error deje la sesión en
    'current transaction is aborted'. Las cargas usan transacciones explícitas.
    """
    conn = psycopg2.connect(config.DATABASE_URL)
    conn.autocommit = autocommit
    register_vector(conn)
    return conn


def preparar_busqueda_vectorial(cur, ef_search: int = 80) -> None:
    """Ajustes de pgvector antes de una búsqueda con filtros.

    hnsw.iterative_scan (pgvector >= 0.8) evita que un WHERE combinado con el índice
    HNSW devuelva menos filas que el LIMIT. En versiones anteriores se ignora.
    """
    cur.execute("SET hnsw.ef_search = %s", (ef_search,))
    en_transaccion = not cur.connection.autocommit
    if en_transaccion:
        cur.execute("SAVEPOINT sp_iterative")
    try:
        cur.execute("SET hnsw.iterative_scan = relaxed_order")
    except psycopg2.Error:
        if en_transaccion:
            cur.execute("ROLLBACK TO SAVEPOINT sp_iterative")
    else:
        if en_transaccion:
            cur.execute("RELEASE SAVEPOINT sp_iterative")


def consultar(conn, sql: str, params=None, vectorial: bool = True):
    """Ejecuta un SELECT y devuelve una lista de diccionarios."""
    with conn.cursor() as cur:
        if vectorial:
            preparar_busqueda_vectorial(cur)
        cur.execute(sql, params)
        columnas = [c.name for c in cur.description]
        return [dict(zip(columnas, fila)) for fila in cur.fetchall()]


def version_pgvector(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        fila = cur.fetchone()
        return fila[0] if fila else "no instalada"

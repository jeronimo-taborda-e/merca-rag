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

from psycopg2.extras import execute_values

from . import chunking, config
from .embeddings import abrir_imagen, texto_para_vectorizar, texto_sin_prefijo

EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".webp"}


class _Transaccion:
    """with _Transaccion(conn) as cur: ...  -> COMMIT si todo sale bien, ROLLBACK si no."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.autocommit_previo = self.conn.autocommit
        self.conn.autocommit = False
        self.cur = self.conn.cursor()
        return self.cur

    def __exit__(self, tipo, *_):
        try:
            if tipo is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.cur.close()
            self.conn.autocommit = self.autocommit_previo
        return False


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


def preparar_chunks(documentos: list[dict], modelos, estrategias=config.ESTRATEGIAS) -> list[dict]:
    """Genera los chunks de cada documento con cada estrategia (sin tocar la base)."""
    filas = []
    for doc in documentos:
        oraciones = vectores = None
        for estrategia in estrategias:
            extra = {}
            if estrategia == "semantico":
                # Las oraciones y sus vectores se calculan una vez por documento
                if oraciones is None:
                    oraciones, vectores = chunking.preparar_oraciones(doc["contenido_texto"], modelos)
                extra = {"oraciones": oraciones, "vectores": vectores}
            chunks, usados = chunking.generar_chunks(doc["contenido_texto"], estrategia, modelos, **extra)
            for i, texto in enumerate(chunks):
                filas.append({"codigo_doc": doc["codigo_doc"], "titulo": doc["titulo"], "estrategia": estrategia,
                              "chunk_id": i, "contenido": texto, "parametros": usados})
    return filas


def cargar_documentos(conn, documentos: list[dict], modelos, estrategias=config.ESTRATEGIAS,
                      con_clip: bool = True) -> dict:
    """Inserta documentos + chunks + vectores e5 (384) y CLIP texto (512) en una transacción.

    Si un documento ya estaba cargado, sus chunks de las estrategias indicadas se regeneran.
    Las consultas que habían recuperado esos chunks se borran (con sus resultados, vectores y
    evaluaciones): sus resultados apuntaban a chunks que ya no existen, así que el experimento
    debe volver a correrse.
    """
    t0 = time.perf_counter()
    filas = preparar_chunks(documentos, modelos, estrategias)

    a_vectorizar = [texto_para_vectorizar(f["titulo"], f["contenido"]) for f in filas]
    for f, texto in zip(filas, a_vectorizar):
        f["n_tokens"] = modelos.contar_tokens(texto)
    excedidos = [f for f in filas if f["n_tokens"] > config.MAX_SEQ_TEXTO]
    if excedidos:
        f = excedidos[0]
        raise ValueError(f"{len(excedidos)} chunks superan {config.MAX_SEQ_TEXTO} tokens "
                         f"(p. ej. {f['codigo_doc']} / {f['estrategia']} / {f['chunk_id']}: {f['n_tokens']})")
    vec_e5 = modelos.embed_pasajes(a_vectorizar) if filas else []
    vec_clip = (modelos.embed_texto_clip([texto_sin_prefijo(f["titulo"], f["contenido"]) for f in filas])
                if (filas and con_clip) else None)

    consultas_borradas = 0
    with _Transaccion(conn) as cur:
        ids_doc = {}
        for doc in documentos:
            id_producto = _id_producto(cur, doc.get("codigo_barras"))
            if doc["tipo"] == "ficha" and id_producto is None:
                raise ValueError(f"La ficha {doc['codigo_doc']} no tiene un codigo_barras de un producto existente")
            if doc["tipo"] != "ficha":
                id_producto = None
            ids_doc[doc["codigo_doc"]] = _upsert_documento(cur, doc, id_producto)

        ids = list(ids_doc.values())
        cur.execute(
            """DELETE FROM consulta WHERE id_consulta IN (
                   SELECT r.id_consulta FROM resultado r
                   JOIN embeddings_texto e ON e.id_embedding = r.id_chunk
                   WHERE e.id_doc = ANY(%s) AND e.estrategia_chunking = ANY(%s))""",
            (ids, list(estrategias)),
        )
        consultas_borradas = cur.rowcount
        # embeddings_texto_clip cae por CASCADE
        cur.execute("DELETE FROM embeddings_texto WHERE id_doc = ANY(%s) AND estrategia_chunking = ANY(%s)",
                    (ids, list(estrategias)))

        if filas:
            valores = [
                (ids_doc[f["codigo_doc"]], f["chunk_id"], f["estrategia"], f["contenido"], f["n_tokens"],
                 json.dumps(f["parametros"], ensure_ascii=False), vec_e5[i], config.MODELO_TEXTO)
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

    por_estrategia = {e: sum(1 for f in filas if f["estrategia"] == e) for e in estrategias}
    return {"documentos": len(documentos), "chunks": len(filas), "por_estrategia": por_estrategia,
            "consultas_borradas": consultas_borradas, "segundos": round(time.perf_counter() - t0, 2)}


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
    data/imagenes/aguacate_hass/  ->  documento FICHA_AGUACATE_HASS (y, por la ficha, su producto).
    Si existe data/imagenes/manifest.csv (archivo, codigo_doc, descripcion, etiquetas separadas
    por ';'), sus valores tienen prioridad.
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
        etiquetas = [e.strip()[:50] for e in (meta.get("etiquetas") or "").split(";") if e.strip()]
        etiquetas = etiquetas or [carpeta.replace("_", " ")[:50]]
        catalogo.append({
            "codigo_img": f"IMG_{_slug(carpeta).upper()[:20]}_{sha[:8]}",
            "ruta": ruta,
            "ruta_archivo": ruta.relative_to(directorio.parent).as_posix(),  # relativa a data/
            "sha256": sha, "ancho": ancho, "alto": alto,
            "codigo_doc": meta.get("codigo_doc") or f"FICHA_{_slug(carpeta).upper()}",
            "descripcion": (meta.get("descripcion") or carpeta.replace("_", " "))[:200],
            "etiquetas": etiquetas,
        })
    return catalogo


def _ids_etiquetas(cur, nombres: list[str]) -> list[int]:
    """Inserta en el catálogo las etiquetas que falten y devuelve sus id (N:M)."""
    ids = []
    for nombre in dict.fromkeys(nombres):
        cur.execute(
            """INSERT INTO etiqueta (nombre) VALUES (%s)
               ON CONFLICT (nombre) DO UPDATE SET nombre = EXCLUDED.nombre
               RETURNING id_etiqueta""",
            (nombre,),
        )
        ids.append(cur.fetchone()[0])
    return ids


def cargar_imagenes(conn, catalogo: list[dict], modelos, lote: int = 16, con_descripcion: bool = True) -> dict:
    """Inserta imagen + etiquetas + vector CLIP de los píxeles (y de la descripción), en una transacción.

    Cada foto pertenece a un único documento (su ficha). Las fotos cuya carpeta no corresponde a
    ningún documento cargado no se insertan y se reportan en `omitidas`.
    """
    t0 = time.perf_counter()
    insertadas, omitidas = 0, []
    with _Transaccion(conn) as cur:
        cur.execute("SELECT codigo_doc, id_doc FROM documento")
        id_doc_por_codigo = dict(cur.fetchall())
        validas = []
        for item in catalogo:
            if item["codigo_doc"] in id_doc_por_codigo:
                validas.append(item)
            else:
                omitidas.append(item["ruta_archivo"])

        for inicio in range(0, len(validas), lote):
            grupo = validas[inicio:inicio + lote]
            vectores = modelos.embed_imagenes([abrir_imagen(c["ruta"]) for c in grupo])
            textos_desc = [f"{c['descripcion']}. {', '.join(c['etiquetas'])}" for c in grupo]
            vec_desc = modelos.embed_texto_clip(textos_desc) if con_descripcion else [None] * len(grupo)
            for item, vector, vdesc in zip(grupo, vectores, vec_desc):
                cur.execute(
                    """
                    INSERT INTO imagen (id_doc, codigo_img, ruta_archivo, sha256, ancho, alto, descripcion)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (sha256) DO UPDATE SET
                        id_doc = EXCLUDED.id_doc, ruta_archivo = EXCLUDED.ruta_archivo,
                        ancho = EXCLUDED.ancho, alto = EXCLUDED.alto, descripcion = EXCLUDED.descripcion
                    RETURNING id_img
                    """,
                    (id_doc_por_codigo[item["codigo_doc"]], item["codigo_img"], item["ruta_archivo"],
                     item["sha256"], item["ancho"], item["alto"], item["descripcion"]),
                )
                id_img = cur.fetchone()[0]
                cur.execute("DELETE FROM imagen_etiqueta WHERE id_img = %s", (id_img,))
                execute_values(cur, "INSERT INTO imagen_etiqueta (id_img, id_etiqueta) VALUES %s",
                               [(id_img, e) for e in _ids_etiquetas(cur, item["etiquetas"])])
                cur.execute(
                    """
                    INSERT INTO embeddings_imagen (id_img, vector_embedding, modelo, vector_descripcion, modelo_descripcion)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id_img) DO UPDATE SET
                        vector_embedding = EXCLUDED.vector_embedding, modelo = EXCLUDED.modelo,
                        vector_descripcion = EXCLUDED.vector_descripcion, modelo_descripcion = EXCLUDED.modelo_descripcion
                    """,
                    (id_img, vector, config.MODELO_CLIP_IMAGEN, vdesc,
                     config.MODELO_CLIP_TEXTO if vdesc is not None else None),
                )
                insertadas += 1
    return {"imagenes": insertadas, "omitidas": omitidas, "segundos": round(time.perf_counter() - t0, 2)}


# ======================================================================= integridad
def verificar_integridad(conn) -> dict:
    """Cuenta filas y comprueba que ningún chunk ni imagen haya quedado sin vector."""
    consultas = {
        "documentos": "SELECT count(*) FROM documento",
        "chunks": "SELECT count(*) FROM embeddings_texto",
        "imagenes": "SELECT count(*) FROM imagen",
        "docs_sin_chunks": """SELECT count(*) FROM documento d
                              WHERE NOT EXISTS (SELECT 1 FROM embeddings_texto e WHERE e.id_doc = d.id_doc)""",
        "docs_sin_las_tres_estrategias": """SELECT count(*) FROM documento d
                              WHERE (SELECT count(DISTINCT estrategia_chunking) FROM embeddings_texto e
                                     WHERE e.id_doc = d.id_doc) < 3""",
        "chunks_sin_vector_clip": """SELECT count(*) FROM embeddings_texto e
                                     LEFT JOIN embeddings_texto_clip c ON c.id_embedding = e.id_embedding
                                     WHERE c.id_embedding IS NULL""",
        "chunks_truncados": f"SELECT count(*) FROM embeddings_texto WHERE n_tokens > {config.MAX_SEQ_TEXTO}",
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

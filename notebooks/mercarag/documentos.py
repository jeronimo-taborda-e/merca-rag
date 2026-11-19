"""Lectura de la fuente de documentos (Markdown, texto plano y PDF).

Cada documento puede traer un encabezado YAML sencillo (front matter):

    ---
    codigo_doc: POL_DOMICILIOS
    tipo: politica            # ficha | politica | manual | guia
    titulo: Política del servicio de domicilios
    codigo_barras: 7700000000017   # opcional: vincula el documento a un producto
    idioma: es
    fecha: 2026-10-01
    fuente: Coordinación de domicilios
    ---

Para PDF (sin encabezado) los metadatos se toman del nombre del archivo y de
data/documentos/manifest_pdf.csv si existe (columnas: archivo, codigo_doc, tipo,
titulo, codigo_barras).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from . import config

TIPOS_VALIDOS = {"ficha", "politica", "manual", "guia"}


def _front_matter(texto: str) -> tuple[dict, str]:
    if not texto.startswith("---"):
        return {}, texto
    partes = texto.split("---", 2)
    if len(partes) < 3:
        return {}, texto
    meta = {}
    for linea in partes[1].strip().splitlines():
        if ":" in linea:
            k, v = linea.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, partes[2]


def markdown_a_texto(md: str) -> str:
    """Quita la sintaxis Markdown y deja texto corrido.

    Los títulos terminan en punto para que el separador de oraciones los trate como
    una oración propia (y no los pegue a la primera oración de la sección).
    """
    lineas = []
    for linea in md.splitlines():
        s = linea.strip()
        if not s:
            lineas.append("")
            continue
        if s.startswith("#"):
            s = s.lstrip("#").strip()
            if s and s[-1] not in ".:?!":
                s += "."
        s = re.sub(r"^[-*]\s+", "", s)           # viñetas
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)  # negrita
        lineas.append(s)
    texto = "\n".join(lineas)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _leer_pdf(ruta: Path) -> str:
    from pypdf import PdfReader
    lector = PdfReader(str(ruta))
    paginas = [(p.extract_text() or "") for p in lector.pages]
    texto = "\n\n".join(paginas)
    texto = re.sub(r"-\n(\w)", r"\1", texto)          # palabras cortadas con guion
    texto = re.sub(r"(?<!\n)\n(?!\n)", " ", texto)    # saltos de línea dentro de párrafos
    return re.sub(r"[ \t]+", " ", texto).strip()


def _manifest_pdf(directorio: Path) -> dict:
    ruta = directorio / "manifest_pdf.csv"
    if not ruta.exists():
        return {}
    with ruta.open(encoding="utf-8") as f:
        return {fila["archivo"]: fila for fila in csv.DictReader(f)}


def cargar_documentos(directorio: Path | None = None) -> list[dict]:
    """Recorre data/documentos/ (recursivo) y devuelve una lista de documentos."""
    directorio = Path(directorio or config.DOCUMENTOS_DIR)
    manifest = _manifest_pdf(directorio)
    documentos = []
    for ruta in sorted(directorio.rglob("*")):
        if ruta.suffix.lower() not in {".md", ".txt", ".pdf"} or ruta.name.startswith("."):
            continue
        if ruta.suffix.lower() == ".pdf":
            meta = dict(manifest.get(ruta.name, {}))
            texto = _leer_pdf(ruta)
        else:
            meta, cuerpo = _front_matter(ruta.read_text(encoding="utf-8"))
            texto = markdown_a_texto(cuerpo) if ruta.suffix.lower() == ".md" else cuerpo.strip()
        if not texto:
            continue
        codigo = meta.get("codigo_doc") or re.sub(r"[^A-Z0-9]+", "_", ruta.stem.upper())
        tipo = meta.get("tipo", "ficha" if "ficha" in ruta.stem.lower() else "guia")
        documentos.append({
            "codigo_doc": codigo,
            "tipo": tipo if tipo in TIPOS_VALIDOS else "guia",
            "titulo": meta.get("titulo") or ruta.stem.replace("_", " ").capitalize(),
            "codigo_barras": meta.get("codigo_barras") or None,
            "idioma": meta.get("idioma", "es"),
            "fecha": meta.get("fecha") or None,
            "fuente": meta.get("fuente") or str(ruta.relative_to(directorio.parent)),
            "contenido_texto": texto,
            "archivo": str(ruta.relative_to(directorio.parent)),
        })
    return documentos

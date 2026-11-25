"""Genera el ERD de MercaRAG en notación Chen (Graphviz)."""
import subprocess, sys

ZONE_COLOR = {"A": "#d9ead3", "B": "#f4cccc", "C": "#d9d2e9"}
ZONE_NAME = {"A": "A. Núcleo comercial", "B": "B. Personas y domicilios", "C": "C. Capa RAG y vectorial"}

# nombre -> (zona, claves, asociativa)
E = {
    "Categoría": ("A", ["id_categoria"], False),
    "Marca": ("A", ["id_marca"], False),
    "Proveedor": ("A", ["id_proveedor"], False),
    "Producto": ("A", ["id_producto"], False),
    "Punto de Venta": ("A", ["id_punto_venta"], False),
    "Inventario": ("A", ["id_punto_venta", "id_producto"], True),
    "Promoción": ("A", ["id_promocion"], False),
    "Promoción Producto": ("A", ["id_promocion", "id_producto"], True),
    "Compra": ("A", ["id_compra"], False),
    "Detalle Compra": ("A", ["id_compra", "id_producto"], True),
    "Usuario": ("B", ["id_usuario"], False),
    "Cliente": ("B", ["id_cliente"], False),
    "Empleado": ("B", ["id_empleado"], False),
    "Administrativo": ("B", ["id_empleado"], False),
    "Conductor": ("B", ["id_empleado"], False),
    "Dirección": ("B", ["id_direccion"], False),
    "Vehículo": ("B", ["id_vehiculo"], False),
    "Domicilio": ("B", ["id_domicilio"], False),
    "Documento": ("C", ["id_doc"], False),
    "Imagen": ("C", ["id_img"], False),
    "Etiqueta": ("C", ["id_etiqueta"], False),
    "Imagen Etiqueta": ("C", ["id_img", "id_etiqueta"], True),
    "Pregunta": ("C", ["id_pregunta"], False),
    "Consulta": ("C", ["id_consulta"], False),
    "Resultado": ("C", ["id_resultado"], False),
    "Evaluación": ("C", ["id_eval"], False),
    "Embeddings Texto": ("C", ["id_embedding"], False),
    "Embeddings Imagen": ("C", ["id_embedding"], False),
    "Query Embeddings": ("C", ["id_qemb"], False),
    "Embeddings Texto CLIP": ("C", ["id_embedding"], False),
    "Pregunta Documento": ("C", ["id_pregunta", "id_doc"], True),
}

# (zona, etiqueta rombo, A, card A, total A, B, card B, total B)
R = [
    ("A", "se clasifica en", "Categoría", "1", False, "Producto", "N", True),
    ("A", "tiene", "Marca", "1", False, "Producto", "N", True),
    ("A", "suministra", "Proveedor", "1", False, "Producto", "N", True),
    ("A", "registra", "Punto de Venta", "1", False, "Compra", "N", True),
    ("A", "realiza", "Cliente", "1", False, "Compra", "N", True),
    ("B", "trabaja en", "Punto de Venta", "1", False, "Empleado", "N", True),
    ("B", "dispone de", "Punto de Venta", "1", False, "Vehículo", "N", True),
    ("B", "registra", "Cliente", "1", False, "Dirección", "N", True),
    ("B", "genera", "Compra", "1", False, "Domicilio", "1", True),
    ("B", "se entrega en", "Dirección", "1", False, "Domicilio", "N", True),
    ("B", "entrega", "Conductor", "1", False, "Domicilio", "N", False),
    ("B", "se usa en", "Vehículo", "1", False, "Domicilio", "N", False),
    ("C", "describe", "Producto", "1", False, "Documento", "N", False),
    ("C", "contiene", "Documento", "1", False, "Imagen", "N", True),
    ("C", "se divide en", "Documento", "1", False, "Embeddings Texto", "N", True),
    ("C", "vectoriza", "Imagen", "1", True, "Embeddings Imagen", "1", True),
    ("C", "formula", "Usuario", "1", False, "Consulta", "N", True),
    ("C", "se ejecuta como", "Pregunta", "1", False, "Consulta", "N", False),
    ("C", "vectoriza", "Consulta", "1", True, "Query Embeddings", "1", True),
    ("C", "recupera", "Consulta", "1", False, "Resultado", "N", True),
    ("C", "aparece en", "Embeddings Texto", "1", False, "Resultado", "N", False),
    ("C", "aparece en", "Imagen", "1", False, "Resultado", "N", False),
    ("C", "se evalúa en", "Consulta", "1", False, "Evaluación", "1", True),
    ("C", "se proyecta en", "Embeddings Texto", "1", False, "Embeddings Texto CLIP", "1", True),
]

# Entidades asociativas: (zona, asociativa, [(entidad, card, total_entidad)])
ASSOC = [
    ("A", "Inventario", [("Producto", "N", False), ("Punto de Venta", "M", False)]),
    ("A", "Promoción Producto", [("Promoción", "N", True), ("Producto", "M", False)]),
    ("A", "Detalle Compra", [("Compra", "N", True), ("Producto", "M", False)]),
    ("C", "Imagen Etiqueta", [("Imagen", "N", False), ("Etiqueta", "M", False)]),
    ("C", "Pregunta Documento", [("Pregunta", "N", True), ("Documento", "M", False)]),
]

# Jerarquías ISA disjuntas (d) y totales
ISA = [
    ("B", "Usuario", ["Cliente", "Empleado"]),
    ("B", "Empleado", ["Administrativo", "Conductor"]),
]

DOUBLE = 'color="black:white:black", penwidth=1.2'


def nid(name):
    return "n_" + "".join(c if c.isalnum() else "_" for c in name)


def build(zones, title):
    zones = set(zones)
    full = len(zones) == 3
    used = set()
    lines = []
    out = lines.append
    out('graph ERD {')
    out('  graph [layout=dot, rankdir=LR, splines=true, nodesep=0.35, ranksep=0.55, fontname="Helvetica", '
        f'fontsize=22, labelloc=t, label="{title}", pad=0.3, dpi=170, newrank=true];')
    out('  node [fontname="Helvetica", fontsize=12];')
    out('  edge [fontname="Helvetica-Bold", fontsize=13, color=black];')

    rels = [r for r in R if r[0] in zones]
    assoc = [a for a in ASSOC if a[0] in zones]
    isas = [i for i in ISA if i[0] in zones]
    for r in rels:
        used.update([r[2], r[5]])
    for a in assoc:
        used.add(a[1]); used.update(e for e, _, _ in a[2])
    for i in isas:
        used.add(i[1]); used.update(i[2])

    for name in sorted(used):
        z, keys, is_assoc = E[name]
        own = z in zones
        if is_assoc:
            out(f'  {nid(name)} [shape=box, label="{name}", image="assoc.png", imagescale=true, '
                f'fixedsize=true, width=2.0, height=0.7, penwidth=0, fontsize=12];')
        elif own:
            out(f'  {nid(name)} [shape=box, style="filled", fillcolor="{ZONE_COLOR[z]}", penwidth=1.6, '
                f'label="{name}", fontsize=14, margin="0.18,0.1"];')
        else:
            out(f'  {nid(name)} [shape=box, style="dashed,filled", fillcolor="#f3f3f3", color="#777777", '
                f'fontcolor="#555555", label="{name}\\n(zona {z})", fontsize=12];')
        if own:
            for k in keys:
                kid = nid(name) + "_" + k
                out(f'  {kid} [shape=ellipse, label=<<U>{k}</U>>, fontsize=10, height=0.3, margin="0.04,0.02"];')
                out(f'  {nid(name)} -- {kid} [penwidth=0.8];')

    for idx, (z, lab, a, ca, ta, b, cb, tb) in enumerate(rels):
        rid = f"r{idx}_{z}"
        out(f'  {rid} [shape=diamond, style=filled, fillcolor="#cfe2f3", label="{lab}", fontsize=11, '
            f'height=0.75, margin="0.05,0.02"];')
        out(f'  {nid(a)} -- {rid} [label="{ca}"{", " + DOUBLE if ta else ""}];')
        out(f'  {rid} -- {nid(b)} [label="{cb}"{", " + DOUBLE if tb else ""}];')

    for z, name, parts in assoc:
        for ent, card, tot in parts:
            # la asociativa siempre participa totalmente (cada fila exige ambas FK)
            out(f'  {nid(ent)} -- {nid(name)} [label="{card}"{", " + DOUBLE if tot else ""}];')

    for idx, (z, sup, subs) in enumerate(isas):
        iid = f"isa{idx}"
        out(f'  {iid} [shape=triangle, style=filled, fillcolor="#fff2cc", label="ISA\\nd", fontsize=11, orientation=90, '
            f'width=0.9, height=0.8, fixedsize=true];')
        out(f'  {nid(sup)} -- {iid} [{DOUBLE}];')
        for s in subs:
            out(f'  {iid} -- {nid(s)} [dir=forward, arrowhead=none, arrowtail=none];')

    if "C" in zones:
        out('  xor_note [shape=note, style=filled, fillcolor="#fffbe6", fontsize=10, '
            'label="XOR: cada Resultado proviene\\nde un chunk (Embeddings Texto)\\no de una Imagen, nunca de ambos"];')
        out(f'  xor_note -- {nid("Resultado")} [style=dotted];')

    out('}')
    return "\n".join(lines)


LEGEND = r'''graph L {
 graph [rankdir=LR, fontname="Helvetica", nodesep=0.3, dpi=170, label="Leyenda (notación Chen)", labelloc=t, fontsize=16];
 node [fontname="Helvetica", fontsize=11];
 e [shape=box, style=filled, fillcolor="#eeeeee", label="Entidad"];
 r [shape=diamond, style=filled, fillcolor="#cfe2f3", label="Relación"];
 a [shape=box, label="Entidad\nasociativa", image="assoc.png", imagescale=true, fixedsize=true, width=1.6, height=0.6, penwidth=0];
 k [shape=ellipse, label=<<U>atributo clave</U>>];
 i [shape=triangle, style=filled, fillcolor="#fff2cc", label="ISA\nd", fixedsize=true, width=0.8, height=0.7];
 x [shape=box, style="dashed,filled", fillcolor="#f3f3f3", color="#777777", label="Entidad de\notra zona"];
 t1 [shape=plaintext, label="Línea doble = participación total"];
 t2 [shape=plaintext, label="Línea simple = participación parcial"];
 t3 [shape=plaintext, label="1, N, M = cardinalidad máxima de la entidad en esa relación"];
 t4 [shape=plaintext, label="ISA d = especialización disjunta; línea doble al supertipo = total"];
 e -- r [label="  ", color="black:white:black"]; r -- a [label=" "];
 k -- i [style=invis]; i -- x [style=invis];
 t1 -- t2 [style=invis]; t3 -- t4 [style=invis];
}'''

if __name__ == "__main__":
    jobs = {
        "erd_completo": ("ABC", "MercaRAG – Diagrama entidad-relación completo (Chen, 31 entidades)"),
        "erd_zona_A": ("A", "Zona A – Núcleo comercial"),
        "erd_zona_B": ("B", "Zona B – Personas y domicilios"),
        "erd_zona_C": ("C", "Zona C – Capa RAG y vectorial"),
    }
    for fn, (zs, title) in jobs.items():
        src = build(zs, title)
        open(fn + ".dot", "w").write(src)
        subprocess.run(["dot", "-Tpng", fn + ".dot", "-o", fn + ".png"], check=True)
        subprocess.run(["dot", "-Tpdf", fn + ".dot", "-o", fn + ".pdf"], check=True)
    open("leyenda.dot", "w").write(LEGEND)
    subprocess.run(["dot", "-Tpng", "leyenda.dot", "-o", "leyenda.png"], check=True)
    print("ok")

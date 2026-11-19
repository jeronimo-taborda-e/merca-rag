"""Genera los datos de prueba de MercaRAG de forma determinista.

Salidas:
  sql/02_datos_dominio.sql      -> catálogo, sedes, personas, compras, domicilios
  data/documentos/fichas/*.md   -> una ficha de producto por cada producto base

Uso (desde la raíz del repositorio):
    python scripts/generar_datos.py

El SQL resultante se ejecuta solo al crear la base (docker-entrypoint-initdb.d),
justo después de schema.sql. Las compras, clientes y domicilios se generan dentro
de PostgreSQL con generate_series + setseed, así el archivo es pequeño y la carga
es reproducible.
"""
from __future__ import annotations

import random
import re
import unicodedata
from pathlib import Path

from catalogo_base import (CATEGORIAS, FACTOR_MARCA, FACTOR_PRESENTACION,
                           PROVEEDORES, PUNTOS_VENTA)

RAIZ = Path(__file__).resolve().parents[1]
SQL_SALIDA = RAIZ / "sql" / "02_datos_dominio.sql"
FICHAS_DIR = RAIZ / "data" / "documentos" / "fichas"

random.seed(42)


def q(valor) -> str:
    """Literal SQL seguro para textos generados por este script."""
    if valor is None:
        return "NULL"
    if isinstance(valor, (int, float)):
        return str(valor)
    return "'" + str(valor).replace("'", "''") + "'"


def slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")


def ean13(n: int) -> str:
    base = f"770{n:09d}"
    suma = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(base))
    return base + str((10 - suma % 10) % 10)


def redondear_precio(valor: float) -> int:
    return int(round(valor / 50.0) * 50)


def main() -> None:
    lineas: list[str] = [
        "-- =====================================================================",
        "-- MercaRAG - Datos de prueba (generado por scripts/generar_datos.py)",
        "-- No editar a mano: modifique catalogo_base.py y vuelva a generar.",
        "-- =====================================================================",
        "BEGIN;",
        "",
    ]

    # ---------------- Catálogos simples ----------------
    lineas.append("INSERT INTO punto_venta (nombre, direccion, barrio, telefono) VALUES")
    lineas.append(",\n".join(f"  ({q(n)}, {q(d)}, {q(b)}, {q(t)})" for n, d, b, t in PUNTOS_VENTA) + ";\n")

    lineas.append("INSERT INTO proveedor (nombre, nit, telefono) VALUES")
    lineas.append(",\n".join(f"  ({q(n)}, {q(nit)}, {q(t)})" for n, nit, t in PROVEEDORES) + ";\n")

    lineas.append("INSERT INTO categoria (nombre) VALUES")
    lineas.append(",\n".join(f"  ({q(c)})" for c in CATEGORIAS) + ";\n")

    marcas = sorted({m for c in CATEGORIAS.values() for m in c["marcas"]})
    lineas.append("INSERT INTO marca (nombre) VALUES")
    lineas.append(",\n".join(f"  ({q(m)})" for m in marcas) + ";\n")

    # ---------------- Productos ----------------
    filas_producto = []
    fichas = []
    n_codigo = 1
    for cat, info in CATEGORIAS.items():
        proveedor_nit = PROVEEDORES[info["proveedor"]][1]
        for nombre, _unidad, presentaciones, precio_base, descripcion in info["productos"]:
            ficha_producto = None
            for i_m, marca in enumerate(info["marcas"]):
                for i_p, pres in enumerate(presentaciones):
                    precio = redondear_precio(precio_base * FACTOR_PRESENTACION[i_p] * FACTOR_MARCA[i_m]
                                              * random.uniform(0.96, 1.04))
                    codigo = ean13(n_codigo)
                    n_codigo += 1
                    nombre_completo = f"{nombre} {marca} {pres}"
                    filas_producto.append(
                        f"  ((SELECT id_categoria FROM categoria WHERE nombre = {q(cat)}), "
                        f"(SELECT id_marca FROM marca WHERE nombre = {q(marca)}), "
                        f"(SELECT id_proveedor FROM proveedor WHERE nit = {q(proveedor_nit)}), "
                        f"{q(nombre_completo)}, {precio}, {q(codigo)})"
                    )
                    if ficha_producto is None:
                        ficha_producto = (codigo, nombre_completo, marca, pres, precio)
            fichas.append((cat, nombre, descripcion, info, presentaciones, ficha_producto))

    lineas.append("INSERT INTO producto (id_categoria, id_marca, id_proveedor, nombre, precio, codigo_barras) VALUES")
    lineas.append(",\n".join(filas_producto) + ";\n")

    # ---------------- Inventario (determinista dentro de PostgreSQL) ----------------
    lineas.append("""-- Inventario: ~85 % de los productos en cada sede; algunos agotados (stock 0)
SELECT setseed(0.42);
INSERT INTO inventario (id_punto_venta, id_producto, stock, stock_minimo, actualizado)
SELECT pv.id_punto_venta, p.id_producto,
       CASE WHEN random() < 0.08 THEN 0 ELSE (random() * 120)::int END,
       5 + (random() * 15)::int,
       DATE '2026-11-01' + (random() * 15)::int
FROM punto_venta pv CROSS JOIN producto p
WHERE random() < 0.85
ORDER BY pv.id_punto_venta, p.id_producto;
""")

    # ---------------- Promociones ----------------
    lineas.append("""INSERT INTO promocion (nombre, tipo_descuento, valor, fecha_inicio, fecha_fin) VALUES
  ('Martes de frutas y verduras', 'porcentaje', 15, DATE '2026-11-01', DATE '2026-12-31'),
  ('Semana láctea', 'porcentaje', 10, DATE '2026-11-10', DATE '2026-11-24'),
  ('Café de Caldas a mitad de precio en la segunda unidad', 'porcentaje', 25, DATE '2026-11-15', DATE '2026-12-15'),
  ('Aseo del hogar: lleve más pague menos', 'valor_fijo', 3000, DATE '2026-11-01', DATE '2026-11-30'),
  ('Mascotas felices', 'porcentaje', 12, DATE '2026-11-05', DATE '2026-12-05'),
  ('Asado del fin de semana', 'valor_fijo', 5000, DATE '2026-11-14', DATE '2026-11-30'),
  ('Navidad en familia', 'porcentaje', 20, DATE '2026-12-01', DATE '2026-12-24'),
  ('Regreso a clases: loncheras', 'porcentaje', 8, DATE '2027-01-10', DATE '2027-02-10');

INSERT INTO promocion_producto (id_promocion, id_producto)
SELECT pr.id_promocion, p.id_producto
FROM promocion pr
JOIN producto p ON TRUE
JOIN categoria c ON c.id_categoria = p.id_categoria
WHERE (pr.nombre LIKE 'Martes de frutas%'  AND c.nombre = 'Frutas y verduras')
   OR (pr.nombre LIKE 'Semana láctea%'     AND c.nombre = 'Lácteos y huevos')
   OR (pr.nombre LIKE 'Café de Caldas%'    AND p.nombre LIKE 'Café%')
   OR (pr.nombre LIKE 'Aseo del hogar%'    AND c.nombre = 'Aseo del hogar')
   OR (pr.nombre LIKE 'Mascotas%'          AND c.nombre = 'Mascotas')
   OR (pr.nombre LIKE 'Asado%'             AND c.nombre = 'Carnes y pescados')
   OR (pr.nombre LIKE 'Navidad%'           AND (p.nombre LIKE 'Ponqué%' OR p.nombre LIKE 'Arequipe%' OR p.nombre LIKE 'Chocolate%'))
   OR (pr.nombre LIKE 'Regreso a clases%'  AND (p.nombre LIKE 'Jugo%' OR p.nombre LIKE 'Yogur%' OR p.nombre LIKE 'Galletas%'));
""")

    # ---------------- Personas, compras y domicilios ----------------
    lineas.append(r"""-- Usuarios internos: 50 empleados (10 por sede: 6 administrativos y 4 conductores)
INSERT INTO usuario (nombre, email, rol)
SELECT 'Empleado ' || g, 'empleado' || g || '@mercarag.co',
       CASE WHEN (g - 1) % 10 < 6 THEN 'administrativo' ELSE 'empleado' END
FROM generate_series(1, 50) g;

INSERT INTO empleado (id_usuario, id_punto_venta, documento, fecha_ingreso, salario)
SELECT u.id_usuario, ((g - 1) / 10) + 1, (1053000000 + g)::text,
       DATE '2020-01-01' + (g * 37) % 2000,
       CASE WHEN (g - 1) % 10 < 6 THEN 2200000 + (g % 6) * 350000 ELSE 1750000 END
FROM generate_series(1, 50) g
JOIN usuario u ON u.email = 'empleado' || g || '@mercarag.co';

INSERT INTO administrativo (id_empleado, area, nivel)
SELECT e.id_empleado,
       (ARRAY['Gerencia de sede', 'Caja', 'Inventario', 'Servicio al cliente', 'Compras', 'Analítica'])[((g - 1) % 10) + 1],
       CASE WHEN (g - 1) % 10 = 0 THEN 'Directivo' ELSE 'Operativo' END
FROM generate_series(1, 50) g
JOIN usuario u ON u.email = 'empleado' || g || '@mercarag.co'
JOIN empleado e ON e.id_usuario = u.id_usuario
WHERE (g - 1) % 10 < 6;

INSERT INTO conductor (id_empleado, licencia, categoria, vencimiento)
SELECT e.id_empleado, 'LIC-' || (17000000 + g), CASE WHEN g % 2 = 0 THEN 'A2' ELSE 'C1' END,
       DATE '2027-06-30' + (g * 11) % 900
FROM generate_series(1, 50) g
JOIN usuario u ON u.email = 'empleado' || g || '@mercarag.co'
JOIN empleado e ON e.id_usuario = u.id_usuario
WHERE (g - 1) % 10 >= 6;

INSERT INTO vehiculo (id_punto_venta, placa, tipo, capacidad_kg, estado)
SELECT pv, placa, tipo, cap, 'disponible'
FROM (VALUES
  (1, 'MZL01A', 'moto', 40), (1, 'MZL02B', 'moto', 40), (1, 'WFK310', 'furgoneta', 800),
  (2, 'MZL03C', 'moto', 40), (2, 'MZL04D', 'moto', 40), (2, 'WFK311', 'camioneta', 600),
  (3, 'MZL05E', 'moto', 40), (3, 'MZL06F', 'moto', 40), (3, 'WFK312', 'furgoneta', 800),
  (4, 'MZL07G', 'moto', 40), (4, 'MZL08H', 'moto', 40), (4, 'WFK313', 'camioneta', 600),
  (5, 'MZL09I', 'moto', 40), (5, 'MZL10J', 'moto', 40), (5, 'WFK314', 'furgoneta', 800)
) v(pv, placa, tipo, cap);

-- Clientes: 5.000 (volumen estimado en la Entrega 1)
SELECT setseed(0.43);
INSERT INTO usuario (nombre, email, rol)
SELECT (ARRAY['Ana','Carlos','Luisa','Andrés','María','Juan','Valentina','Santiago','Camila','Felipe',
              'Laura','Sebastián','Daniela','Mateo','Sara','Julián','Paula','Tomás','Natalia','David'])[1 + (g % 20)]
       || ' ' ||
       (ARRAY['Gómez','Restrepo','Ospina','Giraldo','Londoño','Arango','Valencia','Cardona','Henao','Marín',
              'Zuluaga','Duque','Salazar','Jaramillo','Montoya','Ramírez','Castaño','Hoyos','Toro','Mejía'])[1 + ((g / 20) % 20)],
       'cliente' || g || '@correo.co', 'cliente'
FROM generate_series(1, 5000) g;

INSERT INTO cliente (id_usuario, documento, telefono, fecha_registro)
SELECT u.id_usuario, (30000000 + g * 7)::text, '31' || lpad(((g * 7919) % 100000000)::text, 8, '0'),
       DATE '2022-01-01' + (g % 1400)
FROM generate_series(1, 5000) g
JOIN usuario u ON u.email = 'cliente' || g || '@correo.co';

-- 1 o 2 direcciones por cliente
INSERT INTO direccion (id_cliente, direccion, barrio, referencia)
SELECT c.id_cliente,
       (ARRAY['Calle','Carrera','Avenida','Diagonal'])[1 + (c.id_cliente % 4)] || ' ' || (10 + c.id_cliente % 90)
         || ' # ' || (1 + (c.id_cliente * 3) % 80) || '-' || (1 + (c.id_cliente * 7) % 60),
       (ARRAY['El Cable','Chipre','Milán','Centro','La Enea','Palermo','Laureles','La Francia','Villamaría',
              'San Jorge','Bosques del Norte','La Sultana','Palogrande','Belén','Versalles','El Bosque',
              'Fátima','Villa Pilar'])[1 + (c.id_cliente % 18)],
       CASE WHEN n = 1 THEN 'Casa' ELSE 'Oficina' END
FROM cliente c
CROSS JOIN generate_series(1, 2) n
WHERE n = 1 OR c.id_cliente % 3 = 0;

-- Total de la compra mantenido por trigger (dato derivado, ver Entrega 1)
CREATE OR REPLACE FUNCTION fn_actualizar_total_compra() RETURNS trigger AS $$
BEGIN
    UPDATE compra c
       SET total = COALESCE((SELECT SUM(d.cantidad * d.precio_unitario)
                               FROM detalle_compra d
                              WHERE d.id_compra = c.id_compra), 0)
     WHERE c.id_compra = COALESCE(NEW.id_compra, OLD.id_compra);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Compras: 30.000 en 2026 (≈ 2/3 domicilio -> ~20.000 domicilios, como en la Entrega 1)
SELECT setseed(0.44);
INSERT INTO compra (id_cliente, id_punto_venta, fecha, canal, total)
SELECT 1 + (random() * 4999)::int,
       1 + (random() * 4)::int,
       TIMESTAMP '2026-01-01 07:00' + (random() * 320) * INTERVAL '1 day' + (random() * 14) * INTERVAL '1 hour',
       CASE WHEN random() < 0.67 THEN 'domicilio' ELSE 'tienda' END,
       0
FROM generate_series(1, 30000);

-- 1 a 6 líneas por compra, con productos disponibles en la sede de la compra
SELECT setseed(0.45);
INSERT INTO detalle_compra (id_compra, id_producto, cantidad, precio_unitario)
SELECT DISTINCT ON (x.id_compra, x.id_producto) x.id_compra, x.id_producto, x.cantidad, p.precio
FROM (
    SELECT c.id_compra, 1 + (random() * (SELECT max(id_producto) - 1 FROM producto))::int AS id_producto,
           1 + (random() * 3)::int AS cantidad
    FROM compra c
    CROSS JOIN LATERAL generate_series(1, 1 + (c.id_compra * 7) % 6) l
) x
JOIN producto p ON p.id_producto = x.id_producto
ORDER BY x.id_compra, x.id_producto;

-- El total se calcula una sola vez para la carga masiva y luego lo mantiene el trigger
UPDATE compra c SET total = s.total
FROM (SELECT id_compra, SUM(cantidad * precio_unitario) AS total FROM detalle_compra GROUP BY id_compra) s
WHERE s.id_compra = c.id_compra;

CREATE TRIGGER trg_detalle_compra_total
AFTER INSERT OR UPDATE OR DELETE ON detalle_compra
FOR EACH ROW EXECUTE FUNCTION fn_actualizar_total_compra();

-- Domicilios: uno por cada compra con canal 'domicilio'
SELECT setseed(0.46);
INSERT INTO domicilio (id_compra, id_direccion, id_vehiculo, id_conductor, estado, hora_entrega)
SELECT c.id_compra,
       (SELECT d.id_direccion FROM direccion d WHERE d.id_cliente = c.id_cliente ORDER BY d.id_direccion LIMIT 1),
       v.id_vehiculo,
       co.id_empleado,
       est.estado,
       CASE WHEN est.estado = 'entregado' THEN c.fecha + (30 + random() * 90) * INTERVAL '1 minute' END
FROM compra c
CROSS JOIN LATERAL (
    SELECT CASE WHEN c.fecha > TIMESTAMP '2026-11-15' THEN
                     (ARRAY['pendiente','en_ruta','entregado'])[1 + (c.id_compra % 3)]
                WHEN c.id_compra % 40 = 0 THEN 'cancelado'
                ELSE 'entregado' END AS estado
) est
CROSS JOIN LATERAL (
    SELECT id_vehiculo FROM vehiculo v WHERE v.id_punto_venta = c.id_punto_venta
    ORDER BY (v.id_vehiculo + c.id_compra) % 3 LIMIT 1
) v
CROSS JOIN LATERAL (
    SELECT cd.id_empleado FROM conductor cd JOIN empleado e ON e.id_empleado = cd.id_empleado
    WHERE e.id_punto_venta = c.id_punto_venta
    ORDER BY (cd.id_empleado + c.id_compra) % 4 LIMIT 1
) co
WHERE c.canal = 'domicilio';

COMMIT;

ANALYZE;
""")

    SQL_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SQL_SALIDA.write_text("\n".join(lineas), encoding="utf-8")

    # ---------------- Fichas de producto (documentos para el RAG) ----------------
    FICHAS_DIR.mkdir(parents=True, exist_ok=True)
    for cat, nombre, descripcion, info, presentaciones, (codigo, nombre_completo, marca, pres, precio) in fichas:
        otras_marcas = ", ".join(info["marcas"][1:])
        precio_txt = f"{precio:,}".replace(",", ".")
        texto = f"""---
codigo_doc: FICHA_{slug(nombre).upper()}
tipo: ficha
titulo: Ficha de producto - {nombre}
codigo_barras: {codigo}
idioma: es
fecha: 2026-11-01
fuente: Catálogo MercaRAG
---
# Ficha de producto: {nombre}

## Descripción
{descripcion} En MercaRAG se encuentra en la sección de {cat.lower()}. La referencia de esta ficha es {nombre_completo}, con código de barras {codigo}.

## Presentaciones y marcas
Se vende en las presentaciones {', '.join(presentaciones)}. Además de {marca}, el supermercado maneja las marcas {otras_marcas}. El precio de referencia de la presentación {pres} es de {precio_txt} pesos, y puede variar según la marca y las promociones vigentes de cada sede.

## Conservación y manipulación
{info['conservacion']}

## Disponibilidad
La disponibilidad se consulta en tiempo real en el inventario de cada punto de venta (Cable, Chipre, Milán, Centro y La Enea). Si el producto está agotado en una sede, el servicio de domicilios puede despacharlo desde la sede más cercana que tenga existencias.
"""
        (FICHAS_DIR / f"ficha_{slug(nombre)}.md").write_text(texto, encoding="utf-8")

    print(f"Productos: {len(filas_producto)}  |  Fichas: {len(fichas)}")
    print(f"SQL  -> {SQL_SALIDA.relative_to(RAIZ)}")
    print(f"MD   -> {FICHAS_DIR.relative_to(RAIZ)}/")


if __name__ == "__main__":
    main()

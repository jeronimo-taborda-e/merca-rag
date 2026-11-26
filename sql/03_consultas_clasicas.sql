-- =====================================================================
-- MercaRAG - Consultas SQL clásicas de los requerimientos funcionales
-- Ejecutar con: docker compose exec -T db psql -U mercarag -d mercarag -f /dev/stdin < sql/03_consultas_clasicas.sql
-- (o abrir en DBeaver / pgAdmin). Los valores de ejemplo se pueden cambiar.
-- =====================================================================

-- RF-01. Productos por categoría, rango de precio y proveedor
SELECT p.nombre, m.nombre AS marca, c.nombre AS categoria, pr.nombre AS proveedor, p.precio
FROM producto p
JOIN categoria c  ON c.id_categoria = p.id_categoria
JOIN marca m      ON m.id_marca = p.id_marca
JOIN proveedor pr ON pr.id_proveedor = p.id_proveedor
WHERE c.nombre = 'Café y chocolate'
  AND p.precio BETWEEN 8000 AND 20000
  AND pr.nombre ILIKE '%café de altura%'
ORDER BY p.precio
LIMIT 20;

-- RF-02. Existencias de un producto en un punto de venta específico
SELECT pv.nombre AS sede, p.nombre AS producto, i.stock, i.stock_minimo, i.actualizado,
       CASE WHEN i.stock = 0 THEN 'agotado'
            WHEN i.stock <= i.stock_minimo THEN 'reponer'
            ELSE 'ok' END AS estado
FROM inventario i
JOIN producto p     ON p.id_producto = i.id_producto
JOIN punto_venta pv ON pv.id_punto_venta = i.id_punto_venta
WHERE p.nombre ILIKE 'Leche deslactosada%'
  AND pv.nombre = 'MercaRAG Milán'
ORDER BY p.nombre;

-- RF-03. Estado e historial de los domicilios de un cliente
SELECT d.id_domicilio, co.fecha AS fecha_compra, d.estado, d.hora_entrega,
       round(EXTRACT(EPOCH FROM (d.hora_entrega - co.fecha)) / 60) AS minutos_entrega,
       d.direccion_entrega, d.barrio_entrega, u_cond.nombre AS conductor, v.placa, v.tipo AS vehiculo, co.total
FROM domicilio d
JOIN compra co    ON co.id_compra = d.id_compra     -- único camino del domicilio al cliente
JOIN cliente cl   ON cl.id_cliente = co.id_cliente
LEFT JOIN conductor cd ON cd.id_empleado = d.id_conductor
LEFT JOIN empleado e   ON e.id_empleado = cd.id_empleado
LEFT JOIN usuario u_cond ON u_cond.id_usuario = e.id_usuario
LEFT JOIN vehiculo v ON v.id_vehiculo = d.id_vehiculo
WHERE cl.documento = '30000070'
ORDER BY co.fecha DESC;

-- RF-07a. Ventas por sede y mes
SELECT pv.nombre AS sede, date_trunc('month', c.fecha)::date AS mes,
       count(*) AS compras, sum(c.total) AS ventas, round(avg(c.total)) AS ticket_promedio
FROM compra c
JOIN punto_venta pv ON pv.id_punto_venta = c.id_punto_venta
GROUP BY pv.nombre, mes
ORDER BY mes DESC, ventas DESC
LIMIT 25;

-- RF-07b. Top 10 productos más vendidos (unidades e ingresos)
SELECT p.nombre, c.nombre AS categoria, sum(d.cantidad) AS unidades,
       sum(d.cantidad * d.precio_unitario) AS ingresos
FROM detalle_compra d
JOIN producto p  ON p.id_producto = d.id_producto
JOIN categoria c ON c.id_categoria = p.id_categoria
GROUP BY p.nombre, c.nombre
ORDER BY unidades DESC
LIMIT 10;

-- RF-07c. Rotación de inventario por categoría y sede (unidades vendidas / stock actual)
WITH vendidas AS (
    SELECT co.id_punto_venta, d.id_producto, sum(d.cantidad) AS unidades
    FROM detalle_compra d JOIN compra co ON co.id_compra = d.id_compra
    WHERE co.fecha >= DATE '2026-10-01'
    GROUP BY co.id_punto_venta, d.id_producto
)
SELECT pv.nombre AS sede, c.nombre AS categoria,
       sum(COALESCE(v.unidades, 0)) AS unidades_vendidas,
       sum(i.stock) AS stock_actual,
       round(sum(COALESCE(v.unidades, 0))::numeric / NULLIF(sum(i.stock), 0), 2) AS rotacion
FROM inventario i
JOIN producto p     ON p.id_producto = i.id_producto
JOIN categoria c    ON c.id_categoria = p.id_categoria
JOIN punto_venta pv ON pv.id_punto_venta = i.id_punto_venta
LEFT JOIN vendidas v ON v.id_punto_venta = i.id_punto_venta AND v.id_producto = i.id_producto
GROUP BY pv.nombre, c.nombre
ORDER BY rotacion DESC NULLS LAST
LIMIT 20;

-- RF-07d. Productos por reponer (stock en o por debajo del mínimo)
SELECT pv.nombre AS sede, p.nombre, i.stock, i.stock_minimo
FROM inventario i
JOIN producto p     ON p.id_producto = i.id_producto
JOIN punto_venta pv ON pv.id_punto_venta = i.id_punto_venta
WHERE i.stock <= i.stock_minimo
ORDER BY pv.nombre, i.stock
LIMIT 30;

-- RF-07e. Descuento aplicado por promoción (cada línea de compra registra la promoción usada)
SELECT pr.nombre AS promocion, pr.tipo_descuento, pr.valor,
       count(*)                              AS lineas,
       count(DISTINCT d.id_compra)           AS compras,
       sum(d.cantidad)                       AS unidades,
       sum(d.cantidad * d.precio_lista)      AS ventas_precio_lista,
       sum(d.cantidad * d.descuento)         AS descuento_total,
       sum(d.cantidad * d.precio_unitario)   AS ventas_netas
FROM detalle_compra d
JOIN promocion pr ON pr.id_promocion = d.id_promocion
GROUP BY pr.id_promocion, pr.nombre, pr.tipo_descuento, pr.valor
ORDER BY descuento_total DESC;

-- RF-07f. Detalle de una compra: qué descuento se aplicó en cada línea
SELECT d.id_compra, p.nombre AS producto, d.cantidad, d.precio_lista,
       COALESCE(pr.nombre, '(sin promoción)') AS promocion, d.descuento, d.precio_unitario,
       d.cantidad * d.precio_unitario AS subtotal
FROM detalle_compra d
JOIN producto p ON p.id_producto = d.id_producto
LEFT JOIN promocion pr ON pr.id_promocion = d.id_promocion
WHERE d.id_compra = (SELECT min(id_compra) FROM detalle_compra WHERE id_promocion IS NOT NULL)
ORDER BY p.nombre;

-- RF-08a. Trazabilidad por tipo de consulta y estrategia de chunking
SELECT c.tipo_consulta, c.estrategia_chunking,
       count(DISTINCT c.id_consulta)                AS consultas,
       round(avg(c.tiempo_recuperacion_ms), 1)      AS recuperacion_ms_prom,
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY c.tiempo_recuperacion_ms)::numeric, 1) AS recuperacion_ms_p95,
       round(avg(c.tiempo_total_ms), 1)             AS total_ms_prom,
       round(avg(r.score_similitud) FILTER (WHERE r.posicion = 1), 4) AS score_top1_prom
FROM consulta c
LEFT JOIN resultado r ON r.id_consulta = c.id_consulta
GROUP BY c.tipo_consulta, c.estrategia_chunking
ORDER BY c.tipo_consulta, c.estrategia_chunking;

-- RF-08b. Experimento de chunking: métricas de recuperación y RAGAS por estrategia
--         (una fila por corrida en la vista v_resultados_experimento, ver schema.sql)
SELECT estrategia_chunking,
       count(*)                                  AS corridas,
       round(avg(hit_1), 3)                      AS hit_1,
       round(avg(hit_k), 3)                      AS hit_k,
       round(avg(reciprocal_rank), 3)            AS mrr,
       count(faithfulness)                       AS evaluadas,
       round(avg(faithfulness), 3)               AS faithfulness,
       round(avg(answer_relevancy), 3)           AS answer_relevancy,
       round(avg(context_recall), 3)             AS context_recall,
       round(avg(tiempo_recuperacion_ms), 1)     AS recuperacion_ms
FROM v_resultados_experimento
GROUP BY estrategia_chunking
ORDER BY context_recall DESC NULLS LAST, mrr DESC;

-- RF-08c. Qué chunk y de qué documento recuperó cada corrida de una pregunta
SELECT p.codigo_pregunta, c.estrategia_chunking, r.posicion, d.codigo_doc, e.chunk_id,
       r.score_similitud, (pd.id_doc IS NOT NULL) AS documento_esperado
FROM consulta c
JOIN pregunta p          ON p.id_pregunta = c.id_pregunta
JOIN resultado r         ON r.id_consulta = c.id_consulta
JOIN embeddings_texto e  ON e.id_embedding = r.id_chunk
JOIN documento d         ON d.id_doc = e.id_doc
LEFT JOIN pregunta_documento pd ON pd.id_pregunta = p.id_pregunta AND pd.id_doc = d.id_doc
WHERE p.codigo_pregunta = 'P01'
ORDER BY c.estrategia_chunking, r.posicion;

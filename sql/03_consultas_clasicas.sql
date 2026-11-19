-- =====================================================================
-- MercaRAG - Consultas SQL clásicas de los requerimientos funcionales
-- Ejecutar con: docker compose exec -T db psql -U mercarag -d mercarag -f /dev/stdin < sql/03_consultas_clasicas.sql
-- (o abrir en DBeaver / pgAdmin). Los valores de ejemplo se pueden cambiar.
-- =====================================================================

-- RF-01. Productos por categoría, rango de precio y proveedor
SELECT p.nombre, m.nombre AS marca, c.nombre AS categoria, pr.nombre AS proveedor, p.precio
FROM producto p
JOIN categoria c  ON c.id_categoria = p.id_categoria
LEFT JOIN marca m ON m.id_marca = p.id_marca
LEFT JOIN proveedor pr ON pr.id_proveedor = p.id_proveedor
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
       dir.direccion, dir.barrio, u_cond.nombre AS conductor, v.placa, v.tipo AS vehiculo, co.total
FROM domicilio d
JOIN compra co    ON co.id_compra = d.id_compra
JOIN cliente cl   ON cl.id_cliente = co.id_cliente
JOIN direccion dir ON dir.id_direccion = d.id_direccion
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

-- RF-08. Métricas de calidad por tipo de consulta y estrategia de chunking
SELECT c.tipo_consulta, c.estrategia_chunking,
       count(DISTINCT c.id_consulta)                AS consultas,
       round(avg(c.tiempo_recuperacion_ms), 1)      AS recuperacion_ms_prom,
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY c.tiempo_recuperacion_ms)::numeric, 1) AS recuperacion_ms_p95,
       round(avg(c.tiempo_total_ms), 1)             AS total_ms_prom,
       round(avg(r.score_similitud) FILTER (WHERE r.ranking = 1), 4) AS score_top1_prom,
       round(avg(ev.faithfulness), 3)               AS faithfulness,
       round(avg(ev.answer_relevancy), 3)           AS answer_relevancy,
       round(avg(ev.context_recall), 3)             AS context_recall
FROM consulta c
LEFT JOIN resultado r   ON r.id_consulta = c.id_consulta
LEFT JOIN evaluacion ev ON ev.id_consulta = c.id_consulta
GROUP BY c.tipo_consulta, c.estrategia_chunking
ORDER BY c.tipo_consulta, c.estrategia_chunking;

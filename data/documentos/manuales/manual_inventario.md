---
codigo_doc: MAN_INVENTARIO
tipo: manual
titulo: Manual de control de inventario y reposición
idioma: es
fecha: 2026-07-10
fuente: Operaciones MercaRAG
---
# Manual de control de inventario y reposición

## Inventario por sede
Cada punto de venta lleva su propio inventario. Para cada combinación de producto y sede el sistema guarda el stock actual, el stock mínimo y la fecha de la última actualización. El stock nunca puede ser negativo: si una venta intenta dejar el stock por debajo de cero, la base de datos rechaza la operación y el cajero debe verificar el conteo físico.

## Stock mínimo y alertas de reposición
El stock mínimo es la cantidad a partir de la cual se debe pedir más mercancía. Se calcula con la venta promedio diaria del producto en la sede multiplicada por los días que tarda el proveedor en entregar, más un margen de seguridad de dos días. Cuando el stock de un producto queda igual o por debajo de su mínimo, el producto aparece en el reporte diario de reposición que revisa el encargado de inventario a las 6:00 a. m.

## Conteos cíclicos
En lugar de cerrar la tienda para contar todo, cada semana se cuentan las categorías de mayor rotación (frutas y verduras, lácteos, carnes y bebidas) y cada mes las demás. Si el conteo físico difiere del sistema en más del 2 %, se investiga la causa: errores de digitación, mermas no registradas, devoluciones sin procesar o pérdidas.

## Traslados entre sedes
Cuando una sede tiene exceso de un producto y otra está agotada, se puede hacer un traslado. El traslado descuenta el stock de la sede de origen y lo suma en la de destino en una sola transacción, para que el producto nunca quede contado dos veces ni desaparezca del sistema. Los traslados de refrigerados solo se hacen en vehículos con nevera.

## Rotación de inventario
La rotación indica cuántas veces se vende el inventario promedio de un producto en un periodo. Un producto con alta rotación, como el arroz, la leche o el banano, necesita reposición frecuente y pedidos pequeños. Un producto con baja rotación ocupa espacio y capital, por lo que se pide en menor cantidad o se incluye en una promoción. El reporte mensual de rotación se obtiene comparando las unidades vendidas en las compras del mes con el stock promedio de cada sede.

## Responsabilidades
El encargado de inventario de cada sede aprueba los pedidos a proveedores, revisa las alertas y firma los traslados. El cajero registra las devoluciones el mismo día. El auxiliar de bodega recibe la mercancía, verifica cantidades y fechas y actualiza el stock en el sistema.

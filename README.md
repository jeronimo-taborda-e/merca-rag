# MercaRAG

**MercaRAG** es un sistema de gestión y recuperación de información orientado al contexto de un supermercado en Manizales, que integra una base de datos relacional con tecnologías de búsqueda semántica basadas en *Retrieval-Augmented Generation (RAG)*.

El proyecto organiza y relaciona información sobre productos, categorías, marcas, proveedores, puntos de venta, inventarios, clientes, empleados, compras y domicilios, y gestiona documentos (fichas de producto, políticas, manuales y guías) e imágenes de productos, junto con las consultas, los resultados de recuperación y sus evaluaciones.

La base de datos está en **PostgreSQL**, ejecutada localmente con **Docker** y con la extensión **pgvector** para almacenar y buscar por similitud los *embeddings* de texto e imágenes. El pipeline RAG multimodal sigue el **laboratorio pgvector multimodal** del curso, adaptado al dominio del supermercado y a las **tres estrategias de chunking** definidas en la Entrega 1.

Proyecto académico de **Bases de Datos Relacionales** — Universidad de Caldas.

## Estructura

```
MercaRAG/
├── docker-compose.yml          # db (PostgreSQL 17 + pgvector) y jupyter
├── schema.sql                  # 31 tablas relacionales y vectoriales, triggers, índices HNSW y vista del experimento
├── sql/
│   ├── 02_datos_dominio.sql    # datos de prueba (se cargan solos al crear la base)
│   └── 03_consultas_clasicas.sql  # RF-01, RF-02, RF-03, RF-07, RF-08 (incluye el experimento)
├── scripts/
│   ├── catalogo_base.py        # catálogo base del supermercado
│   └── generar_datos.py        # regenera sql/02_datos_dominio.sql y las fichas
├── data/
│   ├── documentos/             # 93 documentos: fichas/, politicas/, manuales/, guias/
│   ├── imagenes/<producto>/    # fotos del catálogo (ver data/imagenes/LEEME.md)
│   ├── consultas/              # fotos para consultar (no se cargan a la base)
│   ├── evaluacion/preguntas.csv  # 30 preguntas con ground truth y documentos esperados
│   └── resultados/             # CSV del experimento de chunking (los genera el notebook 02)
├── jupyter/                    # Dockerfile y requirements de Jupyter
└── notebooks/
    ├── 00_arranque_docker.ipynb          # verifica conexión, tablas e índices
    ├── 01_rag_multimodal_mercarag.ipynb  # laboratorio multimodal aplicado a MercaRAG
    ├── 02_experimento_chunking.ipynb     # protocolo 30 preguntas × 3 estrategias + RAGAS
    └── mercarag/                         # paquete Python con toda la lógica
```

## Ejecución con Docker

Requisitos: Docker Desktop (con WSL 2 en Windows), 8 GB de RAM, unos 6 GB de disco e internet la primera vez.

1. Revise el archivo `.env` (si no existe, copie `.env.example` como `.env` y cambie la contraseña). Para generar respuestas con el LLM agregue `GROQ_API_KEY` (gratis en console.groq.com/keys); es opcional.
2. Levante los servicios:
   ```
   docker compose up -d --build
   ```
   La primera vez construye Jupyter (PyTorch CPU, spaCy) y crea la base con `schema.sql` + `sql/02_datos_dominio.sql`. Puede tardar 10–15 minutos.
3. (Opcional) Ponga fotos de productos en `data/imagenes/<producto>/` y alguna foto externa en `data/consultas/` (ver `data/imagenes/LEEME.md`).
4. Abra JupyterLab en http://localhost:8889 (token: `JUPYTER_TOKEN` de `.env`) y ejecute en orden:
   `00_arranque_docker` → `01_rag_multimodal_mercarag` → `02_experimento_chunking`.
5. Para DBeaver o pgAdmin: `localhost`, puerto `5434`, credenciales de `.env`.

`schema.sql` y los datos solo se cargan cuando el volumen de la base está vacío. Si cambia el esquema o la contraseña, recree la base (borra los datos):

```
docker compose down -v
docker compose up -d
```

| Acción | Comando |
|---|---|
| Ver estado | `docker compose ps` |
| Ver logs de la base | `docker compose logs -f db` |
| Apagar conservando datos | `docker compose down` |
| Consola SQL | `docker compose exec db psql -U mercarag -d mercarag` |
| Consultas clásicas | `docker compose exec db psql -U mercarag -d mercarag -f /sql/03_consultas_clasicas.sql` |
| Regenerar datos de prueba | `python scripts/generar_datos.py` (y luego `down -v` / `up -d`) |

## Datos de prueba

| Tabla | Filas | | Tabla | Filas |
|---|---|---|---|---|
| punto_venta | 5 | | cliente | 5.000 |
| producto | 1.215 | | compra | 30.000 |
| inventario | ~5.100 | | detalle_compra | ~105.000 |
| promocion | 8 | | domicilio | ~20.000 |
| empleado | 50 (30 administrativos, 20 conductores) | | documento | 93 (81 fichas, 4 políticas, 4 manuales, 4 guías) |

Los datos se generan con semillas fijas (`random.seed`, `setseed`): todos los integrantes obtienen la misma base. El total de cada compra lo mantiene el trigger `trg_detalle_compra_total` (dato derivado, como se definió en la Entrega 1).
Todo el archivo de datos va en una sola transacción: los triggers diferidos de las jerarquías ISA verifican al final que cada usuario y cada empleado tenga la fila de su subtipo.

## Rutas de búsqueda (laboratorio multimodal)

| Ruta | Vectoriza con | Busca en | Requerimiento |
|---|---|---|---|
| Texto → Texto | multilingual-e5-small (384) + texto completo | `embeddings_texto` (por estrategia) | RF-04, RF-06 |
| Texto → Imagen | CLIP texto multilingüe (512) | `embeddings_imagen` | RF-09 |
| Imagen → Imagen | CLIP imagen (512) | `embeddings_imagen` | |
| Imagen → Texto | CLIP imagen (512) | `embeddings_texto_clip` | |
| Productos similares | e5-small (384) | fichas de producto | RF-04 |
| Híbrida | e5-small + filtros SQL | fichas + inventario + sede + precio | RF-05 |

El RAG (RF-06) recupera chunks y fotos, arma el contexto, lo envía a Groq y registra la consulta, sus vectores, cada resultado (el **chunk** o la foto) con su posición y los tiempos (RF-08).

## Estrategias de chunking (Entrega 1, corregida)

Solo se fragmentan los documentos (fichas, políticas, manuales y guías); productos, clientes y compras son filas SQL.
Todos los tamaños se miden con el tokenizador de `intfloat/multilingual-e5-small`, que lee hasta 512 tokens.

| Estrategia | Herramienta | Parámetros (congelados en `config.py`) |
|---|---|---|
| `fijo` | tokenizador del modelo (offsets) | 256 tokens, overlap 32 |
| `oraciones` | spaCy `es_core_news_sm` + agrupación propia | máx. 5 oraciones, overlap 1, tope 464 tokens |
| `semantico` | spaCy + e5-small (oración vs. centroide del chunk) | umbral coseno **0,80 fijo**, tope 464 tokens |

Las tres conviven en `embeddings_texto` (columna `estrategia_chunking`, con un índice HNSW parcial por estrategia).
Cada chunk guarda sus `parametros` (JSONB) y sus `n_tokens` (lo que lee el modelo: `passage: título. chunk`); un `CHECK`
impide guardar uno de más de 512 tokens, así que ninguno se trunca al vectorizar.

## Experimento de chunking (notebook 02)

1. `data/evaluacion/preguntas.csv`: 30 preguntas con su *ground truth* y los documentos que las responden, redactadas antes
   de generar chunks (8 de políticas, 7 de manuales, 7 de fichas, 5 de guías y 3 multidocumento). Se cargan en `pregunta`
   y `pregunta_documento`.
2. Cada pregunta se ejecuta con cada estrategia (90 corridas, `top_k = 5`, mismo LLM con temperatura 0). Cada corrida queda en
   `consulta` (con `id_pregunta` y `estrategia_chunking`) y sus chunks en `resultado`.
3. Métricas: recuperación (hit@1, hit@5, MRR) desde la vista `v_resultados_experimento`, y RAGAS (faithfulness,
   answer_relevancy, context_recall) con un LLM juez, guardadas en `evaluacion`.
4. Comparación pareada por pregunta con la prueba de Wilcoxon (α = 0,05). Ningún parámetro se ajusta mirando las métricas.

## Correcciones de la revisión de la Entrega 1

- **Modelo de texto multilingüe** `intfloat/multilingual-e5-small` (384, igual que el esquema) con prefijos `query:`/`passage:`;
  lee 512 tokens, así que los chunks de 256 entran completos. CLIP de texto multilingüe para las preguntas en español contra fotos.
- **Chunking**: fixed-size de 256/32 medido con el tokenizador del modelo, 5 oraciones, umbral semántico fijo de 0,80 y protocolo.
- **Jerarquías ISA disjuntas y totales** (`usuario.tipo`, `empleado.tipo_empleado`, FK compuestas y triggers diferidos).
- **Imagen con un único dueño** (la ficha); el producto se obtiene por `documento.id_producto`.
- **Etiquetas N:M**: catálogo `etiqueta` + `imagen_etiqueta`.
- **Capa de experimento**: `pregunta` y `pregunta_documento`; `consulta.id_pregunta`/`estrategia_chunking`;
  `resultado.id_chunk` con `CHECK` exclusivo chunk/imagen; `query_embeddings.vector_texto` (384) y `vector_clip` (512);
  `embeddings_imagen` 1:1 (`UNIQUE id_img`).
- Triggers: total de la compra, estrategia del chunk = estrategia de la consulta, evaluación solo con ground truth,
  promoción vigente y descuento derivado en cada línea de compra.

### Recomendaciones adicionales sobre el ERD

- **Domicilio con un solo camino al cliente** (`domicilio → compra → cliente`). Se eliminó la relación
  `Dirección —se entrega en— Domicilio` (y `domicilio.id_direccion`), que daba un segundo dueño y permitía que los dos
  caminos apuntaran a clientes distintos. La dirección de entrega queda como atributos del domicilio
  (`direccion_entrega`, `barrio_entrega`, `referencia`), copiados de la libreta de direcciones del cliente al hacer el
  pedido; así además se conserva dónde se entregó aunque el cliente edite o borre la dirección después.
- **La promoción queda registrada en la compra**: nueva relación `Promoción —se aplica en— Detalle Compra` (1:N,
  parcial). Cada línea guarda `id_promocion` (0 o 1, las promociones no son acumulables), `precio_lista`, `descuento`
  por unidad y `precio_unitario = precio_lista − descuento`. La FK compuesta `(id_promocion, id_producto) →
  promocion_producto` garantiza que la promoción cubra el producto, y `trg_aplicar_promocion` valida la vigencia en la
  fecha de la compra y calcula el descuento. Consultas RF-07e/RF-07f en `sql/03_consultas_clasicas.sql`.

## Notas

- Dentro de los contenedores el servidor de base de datos se llama `db`, no `localhost`.
- Los puertos solo escuchan en este equipo (`127.0.0.1`).
- El modelo `llama-3.3-70b-versatile` del laboratorio fue retirado por Groq; por defecto se usa `openai/gpt-oss-120b`.

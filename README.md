# MercaRAG

**MercaRAG** es un sistema de gestión y recuperación de información orientado al contexto de un supermercado en Manizales, que integra una base de datos relacional con tecnologías de búsqueda semántica basadas en *Retrieval-Augmented Generation (RAG)*.

El proyecto organiza y relaciona información sobre productos, categorías, marcas, proveedores, puntos de venta, inventarios, clientes, empleados, compras y domicilios, y gestiona documentos (fichas de producto, políticas, manuales y guías) e imágenes de productos, junto con las consultas, los resultados de recuperación y sus evaluaciones.

La base de datos está en **PostgreSQL**, ejecutada localmente con **Docker** y con la extensión **pgvector** para almacenar y buscar por similitud los *embeddings* de texto e imágenes. El pipeline RAG multimodal sigue el **laboratorio pgvector multimodal** del curso, adaptado al dominio del supermercado y a las **tres estrategias de chunking** definidas en la Entrega 1.

Proyecto académico de **Bases de Datos Relacionales** — Universidad de Caldas.

## Estructura

```
MercaRAG/
├── docker-compose.yml          # db (PostgreSQL 17 + pgvector) y jupyter
├── schema.sql                  # 28 tablas relacionales y vectoriales + índices HNSW
├── sql/
│   ├── 02_datos_dominio.sql    # datos de prueba (se cargan solos al crear la base)
│   └── 03_consultas_clasicas.sql  # RF-01, RF-02, RF-03, RF-07, RF-08
├── scripts/
│   ├── catalogo_base.py        # catálogo base del supermercado
│   └── generar_datos.py        # regenera sql/02_datos_dominio.sql y las fichas
├── data/
│   ├── documentos/             # 93 documentos: fichas/, politicas/, manuales/, guias/
│   ├── imagenes/<producto>/    # fotos del catálogo (ver data/imagenes/LEEME.md)
│   ├── consultas/              # fotos para consultar (no se cargan a la base)
│   └── resultados/             # CSV del experimento de chunking
├── jupyter/                    # Dockerfile y requirements de Jupyter
└── notebooks/
    ├── 00_arranque_docker.ipynb          # verifica conexión, tablas e índices
    ├── 01_rag_multimodal_mercarag.ipynb  # laboratorio multimodal aplicado a MercaRAG
    ├── 02_experimento_chunking.ipynb     # comparación fijo / oraciones / semántico
    └── mercarag/                         # paquete Python con toda la lógica
```

## Ejecución con Docker

Requisitos: Docker Desktop (con WSL 2 en Windows), 8 GB de RAM, unos 6 GB de disco e internet la primera vez.

1. Revise el archivo `.env` (si no existe, copie `.env.example` como `.env` y cambie la contraseña). Para generar respuestas con el LLM agregue `GROQ_API_KEY` (gratis en console.groq.com/keys); es opcional.
2. Levante los servicios:
   ```
   docker compose up -d --build
   ```
   La primera vez construye Jupyter (PyTorch CPU, spaCy, tiktoken) y crea la base con `schema.sql` + `sql/02_datos_dominio.sql`. Puede tardar 10–15 minutos.
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
| empleado | 50 (30 administrativos, 20 conductores) | | documento | 93 |

Los datos se generan con semillas fijas (`random.seed`, `setseed`): todos los integrantes obtienen la misma base. El total de cada compra lo mantiene el trigger `trg_detalle_compra_total` (dato derivado, como se definió en la Entrega 1).

## Rutas de búsqueda (laboratorio multimodal)

| Ruta | Vectoriza con | Busca en | Requerimiento |
|---|---|---|---|
| Texto → Texto | MiniLM multilingüe (384) | `embeddings_texto` (por estrategia) | RF-06 |
| Texto → Imagen | CLIP texto multilingüe (512) | `embeddings_imagen` | RF-09 |
| Imagen → Imagen | CLIP imagen (512) | `embeddings_imagen` | |
| Imagen → Texto | CLIP imagen (512) | `embeddings_texto_clip` | |
| Productos similares | MiniLM (384) | fichas de producto | RF-04 |
| Híbrida | MiniLM + filtros SQL | fichas + inventario + sede + precio | RF-05 |

El RAG (RF-06) recupera chunks y fotos, arma el contexto, lo envía a Groq y registra la consulta, su vector, cada resultado con su ranking y los tiempos (RF-08).

## Estrategias de chunking (Entrega 1)

| Estrategia | Herramienta | Parámetros |
|---|---|---|
| `fijo` | LangChain `TokenTextSplitter` (cl100k_base) | 512 tokens, overlap 64 |
| `oraciones` | spaCy `es_core_news_sm` | 6 oraciones, overlap 1 |
| `semantico` | Sentence Transformers (MiniLM) | umbral coseno 0,60–0,70 (se elige en el notebook 02) |

Las tres conviven en `embeddings_texto` (columna `estrategia_chunking`, con un índice HNSW parcial por estrategia), y cada chunk guarda sus `parametros` (JSONB) y su `n_tokens` para medir cuánto contexto se pierde por truncamiento.

## Cambios respecto a la Entrega 1

- **Modelo de texto multilingüe**: `paraphrase-multilingual-MiniLM-L12-v2` en lugar de `all-MiniLM-L6-v2`. Misma dimensión (384), pero entrenado para español, que es el idioma de los documentos y de las preguntas (error común señalado en el laboratorio).
- **CLIP de texto multilingüe** (`clip-ViT-B-32-multilingual-v1`) para que una pregunta en español encuentre fotos.
- Tabla nueva `embeddings_texto_clip` (chunks en el espacio CLIP) para la ruta imagen → texto.
- `query_embeddings.vector_clip` (512): la Entrega 1 guardaba la pregunta CLIP en una columna de 384.
- Columnas de trazabilidad y carga idempotente: `documento.codigo_doc/tipo`, `imagen.codigo_img/sha256/ancho/alto`, `consulta.tipo_consulta/respuesta_llm/tiempos`, `resultado.ranking/id_embedding_texto`.
- El catálogo tiene 1.215 productos (81 productos base × 5 marcas × 3 presentaciones) y 93 documentos.

## Notas

- Dentro de los contenedores el servidor de base de datos se llama `db`, no `localhost`.
- Los puertos solo escuchan en este equipo (`127.0.0.1`).
- El modelo `llama-3.3-70b-versatile` del laboratorio fue retirado por Groq; por defecto se usa `openai/gpt-oss-120b`.

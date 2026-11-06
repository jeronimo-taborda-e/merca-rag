# MercaRAG

**MercaRAG** es un sistema de gestión y recuperación de información orientado al contexto de un supermercado, que integra una base de datos relacional con tecnologías de búsqueda semántica basadas en *Retrieval-Augmented Generation (RAG)*.

El proyecto permite organizar y relacionar información sobre productos, categorías, marcas, proveedores, puntos de venta, inventarios, clientes, empleados, compras y domicilios. Además, contempla la gestión de documentos e imágenes asociados a los productos, así como el almacenamiento de consultas, resultados de recuperación y evaluaciones.

La base de datos está diseñada en **PostgreSQL**, ejecutada localmente con **Docker** y con la extensión **pgvector** para almacenar y realizar búsquedas por similitud sobre representaciones vectoriales (*embeddings*) de texto e imágenes.

El modelo incorpora claves primarias y foráneas, restricciones de integridad, relaciones entre entidades e índices convencionales y vectoriales, con el objetivo de mantener la consistencia de los datos y facilitar las consultas tradicionales y semánticas.

MercaRAG se desarrolla como un proyecto académico de **Bases de Datos Relacionales**, enfocado en aplicar conceptos de modelado relacional, integridad de datos, normalización y recuperación de información en un escenario de supermercado.


## Ejecución con Docker

Requisitos: Docker Desktop (con WSL2 en Windows).

1. Revisa el archivo `.env` (si no existe, copia `.env.example` como `.env` y cambia la contraseña).
2. Levanta los servicios:
   ```
   docker compose up -d --build
   ```
   La primera vez descarga las imágenes y construye Jupyter; puede tardar varios minutos.
3. Abre JupyterLab en http://localhost:8889 (token: el valor de `JUPYTER_TOKEN` en `.env`) y ejecuta `notebooks/00_arranque_docker.ipynb`.
4. Para conectarte con DBeaver o pgAdmin usa `localhost`, puerto `5434` y las credenciales de `.env`.

El archivo `schema.sql` se ejecuta automáticamente la primera vez que se crea la base. Si lo modificas, recrea la base (esto borra los datos):

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

Notas:
- Dentro de los contenedores el servidor de base de datos se llama `db`, no `localhost`.
- Los puertos solo escuchan en este equipo (`127.0.0.1`).

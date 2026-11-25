"""MercaRAG: RAG multimodal de un supermercado con PostgreSQL + pgvector.

Módulos:
    config      parámetros congelados (modelos, chunking de la Entrega 1, LLM)
    db          conexión a PostgreSQL y ajustes de pgvector
    documentos  lectura de la fuente de documentos (md, txt, pdf)
    chunking    estrategias fijo / oraciones / semántico (tokens del modelo)
    embeddings  multilingual-e5-small (384) y CLIP ViT-B/32 (512)
    carga       carga transaccional e idempotente + verificación de integridad
    busqueda    rutas texto/imagen y búsqueda híbrida
    rag         contexto, LLM (Groq) y trazabilidad
    evaluacion  conjunto de evaluación, experimento de chunking y métricas RAGAS
"""

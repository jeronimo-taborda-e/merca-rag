-- =====================================================================
-- MercaRAG - Esquema relacional + vectorial (PostgreSQL + pgvector)
-- Se ejecuta automáticamente la primera vez que se crea el volumen de Docker
-- (docker-entrypoint-initdb.d). Para re-ejecutarlo: docker compose down -v
--
-- Cambios respecto a la Entrega 1 (para soportar el laboratorio multimodal):
--   * documento.codigo_doc / tipo          -> carga idempotente (ON CONFLICT)
--   * imagen.codigo_img / sha256 / ancho / alto -> no duplicar fotos
--   * embeddings_texto.n_tokens / parametros    -> experimento de chunking
--   * embeddings_texto_clip (nueva)        -> ruta imagen -> texto (CLIP 512)
--   * query_embeddings.vector_clip         -> preguntas en el espacio CLIP
--   * consulta.tipo_consulta / respuesta_llm / tiempos -> trazabilidad (RF-08)
--   * resultado.ranking / id_embedding_texto     -> qué chunk se recuperó
-- =====================================================================
CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS query_embeddings CASCADE;
DROP TABLE IF EXISTS embeddings_texto_clip CASCADE;
DROP TABLE IF EXISTS embeddings_imagen CASCADE;
DROP TABLE IF EXISTS embeddings_texto CASCADE;
DROP TABLE IF EXISTS evaluacion CASCADE;
DROP TABLE IF EXISTS resultado CASCADE;
DROP TABLE IF EXISTS imagen_etiqueta CASCADE;
DROP TABLE IF EXISTS imagen CASCADE;
DROP TABLE IF EXISTS consulta CASCADE;
DROP TABLE IF EXISTS domicilio CASCADE;
DROP TABLE IF EXISTS detalle_compra CASCADE;
DROP TABLE IF EXISTS conductor CASCADE;
DROP TABLE IF EXISTS administrativo CASCADE;
DROP TABLE IF EXISTS vehiculo CASCADE;
DROP TABLE IF EXISTS direccion CASCADE;
DROP TABLE IF EXISTS empleado CASCADE;
DROP TABLE IF EXISTS compra CASCADE;
DROP TABLE IF EXISTS inventario CASCADE;
DROP TABLE IF EXISTS promocion_producto CASCADE;
DROP TABLE IF EXISTS promocion CASCADE;
DROP TABLE IF EXISTS cliente CASCADE;
DROP TABLE IF EXISTS documento CASCADE;
DROP TABLE IF EXISTS producto CASCADE;
DROP TABLE IF EXISTS proveedor CASCADE;
DROP TABLE IF EXISTS marca CASCADE;
DROP TABLE IF EXISTS categoria CASCADE;
DROP TABLE IF EXISTS punto_venta CASCADE;
DROP TABLE IF EXISTS usuario CASCADE;

CREATE TABLE categoria (
    id_categoria SERIAL PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE marca (
    id_marca SERIAL PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE proveedor (
    id_proveedor SERIAL PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    nit VARCHAR(20) NOT NULL UNIQUE,
    telefono VARCHAR(20)
);

CREATE TABLE punto_venta (
    id_punto_venta SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    direccion VARCHAR(100) NOT NULL,
    barrio VARCHAR(100),
    telefono VARCHAR(20)
);

CREATE TABLE usuario (
    id_usuario SERIAL PRIMARY KEY,
    nombre VARCHAR(120),
    email VARCHAR(150) UNIQUE NOT NULL,
    rol VARCHAR(20) NOT NULL
        CHECK (rol IN ('cliente', 'empleado', 'administrativo'))
);

CREATE TABLE cliente (
    id_cliente SERIAL PRIMARY KEY,
    id_usuario INT NOT NULL UNIQUE,
    documento VARCHAR(30) NOT NULL UNIQUE,
    telefono VARCHAR(20),
    fecha_registro DATE,

    CONSTRAINT fk_cliente_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario)
        ON DELETE RESTRICT
);

CREATE TABLE empleado (
    id_empleado SERIAL PRIMARY KEY,
    id_usuario INT NOT NULL UNIQUE,
    id_punto_venta INT NOT NULL,
    documento VARCHAR(30) NOT NULL UNIQUE,
    fecha_ingreso DATE,
    salario NUMERIC(10,2),

    CONSTRAINT fk_empleado_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario)
        ON DELETE RESTRICT,

    CONSTRAINT fk_empleado_punto_venta
        FOREIGN KEY (id_punto_venta)
        REFERENCES punto_venta(id_punto_venta)
        ON DELETE RESTRICT,

    CONSTRAINT ck_empleado_salario
        CHECK (salario > 0)
);

CREATE TABLE administrativo (
    id_empleado INT PRIMARY KEY,
    area VARCHAR(100) NOT NULL,
    nivel VARCHAR(50),

    CONSTRAINT fk_administrativo_empleado
        FOREIGN KEY (id_empleado)
        REFERENCES empleado(id_empleado)
        ON DELETE RESTRICT
);

CREATE TABLE conductor (
    id_empleado INT PRIMARY KEY,
    licencia VARCHAR(30) NOT NULL UNIQUE,
    categoria VARCHAR(30),
    vencimiento DATE,

    CONSTRAINT fk_conductor_empleado
        FOREIGN KEY (id_empleado)
        REFERENCES empleado(id_empleado)
        ON DELETE RESTRICT
);

CREATE TABLE producto (
    id_producto SERIAL PRIMARY KEY,
    id_categoria INT NOT NULL,
    id_marca INT,
    id_proveedor INT,
    nombre VARCHAR(150) NOT NULL,
    precio NUMERIC(10,2) NOT NULL,
    codigo_barras VARCHAR(20) UNIQUE,

    CONSTRAINT fk_producto_categoria
        FOREIGN KEY (id_categoria)
        REFERENCES categoria(id_categoria)
        ON DELETE RESTRICT,

    CONSTRAINT fk_producto_marca
        FOREIGN KEY (id_marca)
        REFERENCES marca(id_marca)
        ON DELETE SET NULL,

    CONSTRAINT fk_producto_proveedor
        FOREIGN KEY (id_proveedor)
        REFERENCES proveedor(id_proveedor)
        ON DELETE SET NULL,

    CONSTRAINT ck_producto_precio
        CHECK (precio >= 0)
);

CREATE TABLE promocion (
    id_promocion SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    tipo_descuento VARCHAR(20) NOT NULL
        CHECK (tipo_descuento IN ('porcentaje', 'valor_fijo')),
    valor NUMERIC(10,2) NOT NULL,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,

    CONSTRAINT ck_promocion_valor
        CHECK (valor > 0),

    CONSTRAINT ck_promocion_fechas
        CHECK (fecha_fin >= fecha_inicio)
);

CREATE TABLE promocion_producto (
    id_promocion INT NOT NULL,
    id_producto INT NOT NULL,

    CONSTRAINT pk_promocion_producto
        PRIMARY KEY (id_promocion, id_producto),

    CONSTRAINT fk_promocion_producto_promocion
        FOREIGN KEY (id_promocion)
        REFERENCES promocion(id_promocion)
        ON DELETE RESTRICT,

    CONSTRAINT fk_promocion_producto_producto
        FOREIGN KEY (id_producto)
        REFERENCES producto(id_producto)
        ON DELETE RESTRICT
);

CREATE TABLE inventario (
    id_punto_venta INT NOT NULL,
    id_producto INT NOT NULL,
    stock INT NOT NULL,
    stock_minimo INT NOT NULL,
    actualizado DATE DEFAULT CURRENT_DATE,

    CONSTRAINT pk_inventario
        PRIMARY KEY (id_punto_venta, id_producto),

    CONSTRAINT ck_inventario_stock
        CHECK (stock >= 0),

    CONSTRAINT ck_inventario_stock_minimo
        CHECK (stock_minimo >= 0),

    CONSTRAINT fk_inventario_punto_venta
        FOREIGN KEY (id_punto_venta)
        REFERENCES punto_venta(id_punto_venta)
        ON DELETE RESTRICT,

    CONSTRAINT fk_inventario_producto
        FOREIGN KEY (id_producto)
        REFERENCES producto(id_producto)
        ON DELETE RESTRICT
);

CREATE TABLE compra (
    id_compra SERIAL PRIMARY KEY,
    id_cliente INT NOT NULL,
    id_punto_venta INT NOT NULL,
    fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    canal VARCHAR(20) NOT NULL
        CHECK (canal IN ('tienda', 'domicilio')),
    total NUMERIC(10,2),

    CONSTRAINT ck_compra_total
        CHECK (total >= 0),

    CONSTRAINT fk_compra_cliente
        FOREIGN KEY (id_cliente)
        REFERENCES cliente(id_cliente)
        ON DELETE RESTRICT,

    CONSTRAINT fk_compra_punto_venta
        FOREIGN KEY (id_punto_venta)
        REFERENCES punto_venta(id_punto_venta)
        ON DELETE RESTRICT
);

CREATE TABLE detalle_compra (
    id_compra INT NOT NULL,
    id_producto INT NOT NULL,
    cantidad INT NOT NULL,
    precio_unitario NUMERIC(10,2) NOT NULL,

    CONSTRAINT pk_detalle_compra
        PRIMARY KEY (id_compra, id_producto),

    CONSTRAINT ck_detalle_compra_cantidad
        CHECK (cantidad > 0),

    CONSTRAINT ck_detalle_compra_precio
        CHECK (precio_unitario >= 0),

    CONSTRAINT fk_detalle_compra_compra
        FOREIGN KEY (id_compra)
        REFERENCES compra(id_compra)
        ON DELETE RESTRICT,

    CONSTRAINT fk_detalle_compra_producto
        FOREIGN KEY (id_producto)
        REFERENCES producto(id_producto)
        ON DELETE RESTRICT
);

CREATE TABLE direccion (
    id_direccion SERIAL PRIMARY KEY,
    id_cliente INT NOT NULL,
    direccion VARCHAR(200) NOT NULL,
    barrio VARCHAR(100),
    referencia VARCHAR(250),

    CONSTRAINT fk_direccion_cliente
        FOREIGN KEY (id_cliente)
        REFERENCES cliente(id_cliente)
        ON DELETE RESTRICT
);

CREATE TABLE vehiculo (
    id_vehiculo SERIAL PRIMARY KEY,
    id_punto_venta INT NOT NULL,
    placa VARCHAR(20) NOT NULL UNIQUE,
    tipo VARCHAR(20) NOT NULL
        CHECK (tipo IN ('moto', 'furgoneta', 'camioneta')),
    capacidad_kg NUMERIC(10,2),
    estado VARCHAR(20) NOT NULL DEFAULT 'disponible'
        CHECK (estado IN ('disponible', 'en_ruta', 'mantenimiento')),

    CONSTRAINT ck_vehiculo_capacidad
        CHECK (capacidad_kg > 0),

    CONSTRAINT fk_vehiculo_punto_venta
        FOREIGN KEY (id_punto_venta)
        REFERENCES punto_venta(id_punto_venta)
        ON DELETE RESTRICT
);

CREATE TABLE domicilio (
    id_domicilio SERIAL PRIMARY KEY,
    id_compra INT NOT NULL UNIQUE,
    id_direccion INT NOT NULL,
    id_vehiculo INT,
    id_conductor INT,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente', 'en_ruta', 'entregado', 'cancelado')),
    hora_entrega TIMESTAMP,

    CONSTRAINT fk_domicilio_compra
        FOREIGN KEY (id_compra)
        REFERENCES compra(id_compra)
        ON DELETE RESTRICT,

    CONSTRAINT fk_domicilio_direccion
        FOREIGN KEY (id_direccion)
        REFERENCES direccion(id_direccion)
        ON DELETE RESTRICT,

    CONSTRAINT fk_domicilio_vehiculo
        FOREIGN KEY (id_vehiculo)
        REFERENCES vehiculo(id_vehiculo)
        ON DELETE RESTRICT,

    CONSTRAINT fk_domicilio_conductor
        FOREIGN KEY (id_conductor)
        REFERENCES conductor(id_empleado)
        ON DELETE RESTRICT
);

CREATE TABLE documento (
    id_doc SERIAL PRIMARY KEY,
    id_producto INT,
    codigo_doc VARCHAR(60) NOT NULL UNIQUE,
    tipo VARCHAR(20) NOT NULL DEFAULT 'ficha'
        CHECK (tipo IN ('ficha', 'politica', 'manual', 'guia')),
    titulo VARCHAR(200) NOT NULL,
    idioma VARCHAR(10) NOT NULL,
    fecha DATE,
    fuente VARCHAR(255),
    contenido_texto TEXT NOT NULL,

    CONSTRAINT fk_documento_producto
        FOREIGN KEY (id_producto)
        REFERENCES producto(id_producto)
        ON DELETE SET NULL
);

CREATE TABLE imagen (
    id_img SERIAL PRIMARY KEY,
    id_doc INT,
    id_producto INT,
    codigo_img VARCHAR(60) NOT NULL UNIQUE,
    ruta_archivo TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL UNIQUE,
    ancho INT CHECK (ancho > 0),
    alto INT CHECK (alto > 0),
    descripcion TEXT,

    CONSTRAINT fk_imagen_documento
        FOREIGN KEY (id_doc)
        REFERENCES documento(id_doc)
        ON DELETE SET NULL,

    CONSTRAINT fk_imagen_producto
        FOREIGN KEY (id_producto)
        REFERENCES producto(id_producto)
        ON DELETE SET NULL
);

CREATE TABLE imagen_etiqueta (
    id_img_etiqueta SERIAL PRIMARY KEY,
    id_img INT NOT NULL,
    etiqueta VARCHAR(100) NOT NULL,

    CONSTRAINT uq_imagen_etiqueta
        UNIQUE (id_img, etiqueta),

    CONSTRAINT fk_imagen_etiqueta_imagen
        FOREIGN KEY (id_img)
        REFERENCES imagen(id_img)
        ON DELETE CASCADE
);

CREATE TABLE consulta (
    id_consulta SERIAL PRIMARY KEY,
    id_usuario INT NOT NULL,
    texto_pregunta TEXT NOT NULL,
    tipo_consulta VARCHAR(20) NOT NULL DEFAULT 'texto_texto'
        CHECK (tipo_consulta IN ('texto_texto', 'texto_imagen', 'imagen_imagen',
                                 'imagen_texto', 'hibrida', 'rag')),
    estrategia_chunking VARCHAR(20)
        CHECK (estrategia_chunking IN ('fijo', 'oraciones', 'semantico')),
    ruta_imagen_consulta TEXT,
    respuesta_llm TEXT,
    modelo_llm VARCHAR(100),
    tiempo_recuperacion_ms NUMERIC(10,2) CHECK (tiempo_recuperacion_ms >= 0),
    tiempo_total_ms NUMERIC(10,2) CHECK (tiempo_total_ms >= 0),
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_consulta_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario)
        ON DELETE RESTRICT
);

CREATE TABLE resultado (
    id_resultado SERIAL PRIMARY KEY,
    id_consulta INT NOT NULL,
    id_doc INT,
    id_img INT,
    id_embedding_texto INT,
    ranking INT NOT NULL CHECK (ranking > 0),
    score_similitud NUMERIC(10,8) NOT NULL,

    CONSTRAINT uq_resultado_ranking
        UNIQUE (id_consulta, ranking),

    CONSTRAINT ck_resultado_recurso
        CHECK (id_doc IS NOT NULL OR id_img IS NOT NULL),

    CONSTRAINT fk_resultado_consulta
        FOREIGN KEY (id_consulta)
        REFERENCES consulta(id_consulta)
        ON DELETE RESTRICT,

    CONSTRAINT fk_resultado_documento
        FOREIGN KEY (id_doc)
        REFERENCES documento(id_doc)
        ON DELETE RESTRICT,

    CONSTRAINT fk_resultado_imagen
        FOREIGN KEY (id_img)
        REFERENCES imagen(id_img)
        ON DELETE RESTRICT
);
-- La FK hacia el chunk se agrega después de crear embeddings_texto (ver abajo).

CREATE TABLE evaluacion (
    id_eval SERIAL PRIMARY KEY,
    id_consulta INT NOT NULL UNIQUE,
    faithfulness NUMERIC(4,3),
    answer_relevancy NUMERIC(4,3),
    context_recall NUMERIC(4,3),
    modelo_eval VARCHAR(100),
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_evaluacion_faithfulness
        CHECK (faithfulness BETWEEN 0 AND 1),

    CONSTRAINT ck_evaluacion_answer_relevancy
        CHECK (answer_relevancy BETWEEN 0 AND 1),

    CONSTRAINT ck_evaluacion_context_recall
        CHECK (context_recall BETWEEN 0 AND 1),

    CONSTRAINT fk_evaluacion_consulta
        FOREIGN KEY (id_consulta)
        REFERENCES consulta(id_consulta)
        ON DELETE RESTRICT
);

-- =====================================================================
-- EMBEDDINGS
-- Debemos tener pgvector.
-- =====================================================================

CREATE TABLE embeddings_texto (
    id_embedding SERIAL PRIMARY KEY,
    id_doc INT NOT NULL,
    chunk_id INT NOT NULL,
    estrategia_chunking VARCHAR(20) NOT NULL
        CHECK (estrategia_chunking IN ('fijo', 'oraciones', 'semantico')),
    contenido_chunk TEXT NOT NULL,
    n_tokens INT CHECK (n_tokens > 0),
    parametros JSONB,
    vector_embedding VECTOR(384) NOT NULL,
    modelo VARCHAR(100),

    CONSTRAINT uq_embeddings_texto_chunk
        UNIQUE (id_doc, estrategia_chunking, chunk_id),

    CONSTRAINT fk_embeddings_texto_documento
        FOREIGN KEY (id_doc)
        REFERENCES documento(id_doc)
        ON DELETE RESTRICT
);

-- Mismo chunk, pero en el espacio CLIP (512): permite la ruta imagen -> texto.
-- 1:1 con embeddings_texto; si se borra el chunk se borra su vector CLIP.
CREATE TABLE embeddings_texto_clip (
    id_embedding INT PRIMARY KEY,
    vector_embedding VECTOR(512) NOT NULL,
    modelo VARCHAR(100),

    CONSTRAINT fk_embeddings_texto_clip_chunk
        FOREIGN KEY (id_embedding)
        REFERENCES embeddings_texto(id_embedding)
        ON DELETE CASCADE
);

CREATE TABLE embeddings_imagen (
    id_embedding SERIAL PRIMARY KEY,
    id_img INT NOT NULL,
    vector_embedding VECTOR(512) NOT NULL,
    modelo VARCHAR(100),

    CONSTRAINT uq_embeddings_imagen_modelo
        UNIQUE (id_img, modelo),

    CONSTRAINT fk_embeddings_imagen_imagen
        FOREIGN KEY (id_img)
        REFERENCES imagen(id_img)
        ON DELETE RESTRICT
);

CREATE TABLE query_embeddings (
    id_qemb SERIAL PRIMARY KEY,
    id_consulta INT NOT NULL UNIQUE,
    vector_embedding VECTOR(384),          -- pregunta en el espacio MiniLM
    vector_clip VECTOR(512),               -- pregunta (texto o foto) en el espacio CLIP
    modelo VARCHAR(100),

    CONSTRAINT ck_query_embeddings_algun_vector
        CHECK (vector_embedding IS NOT NULL OR vector_clip IS NOT NULL),

    CONSTRAINT fk_query_embeddings_consulta
        FOREIGN KEY (id_consulta)
        REFERENCES consulta(id_consulta)
        ON DELETE RESTRICT
);

-- Resultado -> chunk exacto recuperado. SET NULL: si se recarga un documento
-- (se regeneran sus chunks) el historial de consultas conserva el id_doc.
ALTER TABLE resultado
    ADD CONSTRAINT fk_resultado_chunk
    FOREIGN KEY (id_embedding_texto)
    REFERENCES embeddings_texto(id_embedding)
    ON DELETE SET NULL;

CREATE INDEX idx_producto_categoria
    ON producto(id_categoria);

CREATE INDEX idx_producto_marca
    ON producto(id_marca);

CREATE INDEX idx_producto_proveedor
    ON producto(id_proveedor);

CREATE INDEX idx_promocion_producto_producto
    ON promocion_producto(id_producto);

CREATE INDEX idx_inventario_producto
    ON inventario(id_producto);

CREATE INDEX idx_empleado_punto_venta
    ON empleado(id_punto_venta);

CREATE INDEX idx_compra_cliente
    ON compra(id_cliente);

CREATE INDEX idx_compra_punto_venta
    ON compra(id_punto_venta);

CREATE INDEX idx_detalle_compra_producto
    ON detalle_compra(id_producto);

CREATE INDEX idx_direccion_cliente
    ON direccion(id_cliente);

CREATE INDEX idx_vehiculo_punto_venta
    ON vehiculo(id_punto_venta);

CREATE INDEX idx_domicilio_direccion
    ON domicilio(id_direccion);

CREATE INDEX idx_domicilio_vehiculo
    ON domicilio(id_vehiculo);

CREATE INDEX idx_domicilio_conductor
    ON domicilio(id_conductor);

CREATE INDEX idx_documento_producto
    ON documento(id_producto);

CREATE INDEX idx_imagen_documento
    ON imagen(id_doc);

CREATE INDEX idx_imagen_producto
    ON imagen(id_producto);

CREATE INDEX idx_consulta_usuario
    ON consulta(id_usuario);

CREATE INDEX idx_resultado_consulta
    ON resultado(id_consulta);

CREATE INDEX idx_resultado_documento
    ON resultado(id_doc);

CREATE INDEX idx_resultado_imagen
    ON resultado(id_img);

CREATE INDEX idx_embeddings_imagen_imagen
    ON embeddings_imagen(id_img);

CREATE INDEX idx_imagen_etiqueta_etiqueta
    ON imagen_etiqueta(etiqueta);

CREATE INDEX idx_documento_idioma_fecha
    ON documento(idioma, fecha);

CREATE INDEX idx_embeddings_texto_documento
    ON embeddings_texto(id_doc, estrategia_chunking);

CREATE INDEX idx_resultado_chunk
    ON resultado(id_embedding_texto);

-- Texto completo (español) sobre los chunks: parte léxica de la búsqueda híbrida
-- (busqueda.buscar_texto_texto). La expresión debe ser idéntica a la de la consulta.
CREATE INDEX idx_emb_texto_fts
    ON embeddings_texto
    USING gin (to_tsvector('spanish', contenido_chunk));

CREATE INDEX idx_inventario_punto_venta_stock
    ON inventario(id_punto_venta, id_producto) WHERE stock > 0;

CREATE INDEX idx_producto_precio
    ON producto(precio);

-- =====================================================================
-- 11. ÍNDICES VECTORIALES (pgvector, HNSW, distancia coseno)
-- =====================================================================

CREATE INDEX idx_emb_texto_hnsw_fijo
    ON embeddings_texto
    USING hnsw (vector_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE estrategia_chunking = 'fijo';

CREATE INDEX idx_emb_texto_hnsw_oraciones
    ON embeddings_texto
    USING hnsw (vector_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE estrategia_chunking = 'oraciones';

CREATE INDEX idx_emb_texto_hnsw_semantico
    ON embeddings_texto
    USING hnsw (vector_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE estrategia_chunking = 'semantico';

CREATE INDEX idx_emb_imagen_hnsw
    ON embeddings_imagen
    USING hnsw (vector_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_emb_texto_clip_hnsw
    ON embeddings_texto_clip
    USING hnsw (vector_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

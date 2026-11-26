
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------- limpieza
DROP VIEW IF EXISTS v_resultados_experimento CASCADE;
DROP TABLE IF EXISTS
    evaluacion, resultado, query_embeddings, consulta, pregunta_documento, pregunta,
    embeddings_texto_clip, embeddings_texto, embeddings_imagen,
    imagen_etiqueta, etiqueta, imagen, documento,
    domicilio, detalle_compra, compra, vehiculo, direccion,
    conductor, administrativo, empleado, cliente, usuario,
    inventario, promocion_producto, promocion, producto,
    proveedor, marca, categoria, punto_venta
    CASCADE;
DROP FUNCTION IF EXISTS fn_actualizar_total_compra() CASCADE;
DROP FUNCTION IF EXISTS fn_validar_resultado() CASCADE;
DROP FUNCTION IF EXISTS fn_validar_evaluacion() CASCADE;
DROP FUNCTION IF EXISTS fn_validar_direccion_domicilio() CASCADE;   -- obsoleta (ya no hay FK domicilio -> direccion)
DROP FUNCTION IF EXISTS fn_aplicar_promocion() CASCADE;
DROP FUNCTION IF EXISTS fn_validar_isa_usuario() CASCADE;
DROP FUNCTION IF EXISTS fn_validar_isa_empleado() CASCADE;



CREATE TABLE punto_venta (
    id_punto_venta  SERIAL        CONSTRAINT pk_punto_venta PRIMARY KEY,
    nombre          VARCHAR(100)  NOT NULL CONSTRAINT uq_punto_venta_nombre UNIQUE,
    direccion       VARCHAR(100)  NOT NULL,
    barrio          VARCHAR(100),
    telefono        VARCHAR(20)
);

CREATE TABLE categoria (
    id_categoria    SERIAL        CONSTRAINT pk_categoria PRIMARY KEY,
    nombre          VARCHAR(80)   NOT NULL CONSTRAINT uq_categoria_nombre UNIQUE
);

CREATE TABLE marca (
    id_marca        SERIAL        CONSTRAINT pk_marca PRIMARY KEY,
    nombre          VARCHAR(80)   NOT NULL CONSTRAINT uq_marca_nombre UNIQUE
);

CREATE TABLE proveedor (
    id_proveedor    SERIAL        CONSTRAINT pk_proveedor PRIMARY KEY,
    nombre          VARCHAR(120)  NOT NULL,
    nit             VARCHAR(20)   NOT NULL CONSTRAINT uq_proveedor_nit UNIQUE,
    telefono        VARCHAR(20)
);

CREATE TABLE producto (
    id_producto     SERIAL        CONSTRAINT pk_producto PRIMARY KEY,
    id_categoria    INT           NOT NULL,
    id_marca        INT           NOT NULL,
    id_proveedor    INT           NOT NULL,
    nombre          VARCHAR(150)  NOT NULL,
    precio          NUMERIC(10,2) NOT NULL CONSTRAINT ck_producto_precio CHECK (precio > 0),
    codigo_barras   VARCHAR(20)   CONSTRAINT uq_producto_codigo_barras UNIQUE,
    CONSTRAINT fk_producto_categoria FOREIGN KEY (id_categoria) REFERENCES categoria(id_categoria) ON DELETE RESTRICT,
    CONSTRAINT fk_producto_marca     FOREIGN KEY (id_marca)     REFERENCES marca(id_marca)         ON DELETE RESTRICT,
    CONSTRAINT fk_producto_proveedor FOREIGN KEY (id_proveedor) REFERENCES proveedor(id_proveedor) ON DELETE RESTRICT
);

CREATE TABLE inventario (
    id_punto_venta  INT           NOT NULL,
    id_producto     INT           NOT NULL,
    stock           INT           NOT NULL CONSTRAINT ck_inventario_stock CHECK (stock >= 0),
    stock_minimo    INT           NOT NULL DEFAULT 0 CONSTRAINT ck_inventario_stock_minimo CHECK (stock_minimo >= 0),
    actualizado     DATE          NOT NULL DEFAULT CURRENT_DATE,
    CONSTRAINT pk_inventario PRIMARY KEY (id_punto_venta, id_producto),
    CONSTRAINT fk_inventario_punto_venta FOREIGN KEY (id_punto_venta) REFERENCES punto_venta(id_punto_venta) ON DELETE RESTRICT,
    CONSTRAINT fk_inventario_producto    FOREIGN KEY (id_producto)    REFERENCES producto(id_producto)       ON DELETE RESTRICT
);

CREATE TABLE promocion (
    id_promocion    SERIAL        CONSTRAINT pk_promocion PRIMARY KEY,
    nombre          VARCHAR(150)  NOT NULL,
    tipo_descuento  VARCHAR(20)   NOT NULL CONSTRAINT ck_promocion_tipo CHECK (tipo_descuento IN ('porcentaje','valor_fijo')),
    valor           NUMERIC(10,2) NOT NULL CONSTRAINT ck_promocion_valor CHECK (valor > 0),
    fecha_inicio    DATE          NOT NULL,
    fecha_fin       DATE          NOT NULL,
    CONSTRAINT ck_promocion_fechas     CHECK (fecha_fin >= fecha_inicio),
    CONSTRAINT ck_promocion_porcentaje CHECK (tipo_descuento <> 'porcentaje' OR valor <= 100)
);

CREATE TABLE promocion_producto (
    id_promocion    INT NOT NULL,
    id_producto     INT NOT NULL,
    CONSTRAINT pk_promocion_producto PRIMARY KEY (id_promocion, id_producto),
    CONSTRAINT fk_promocion_producto_promocion FOREIGN KEY (id_promocion) REFERENCES promocion(id_promocion) ON DELETE CASCADE,
    CONSTRAINT fk_promocion_producto_producto  FOREIGN KEY (id_producto)  REFERENCES producto(id_producto)   ON DELETE RESTRICT
);



CREATE TABLE usuario (
    id_usuario      SERIAL        CONSTRAINT pk_usuario PRIMARY KEY,
    nombre          VARCHAR(120)  NOT NULL,
    email           VARCHAR(150)  NOT NULL CONSTRAINT uq_usuario_email UNIQUE,
    tipo            VARCHAR(10)   NOT NULL CONSTRAINT ck_usuario_tipo CHECK (tipo IN ('cliente','empleado')),
    CONSTRAINT uq_usuario_id_tipo UNIQUE (id_usuario, tipo)
);

CREATE TABLE cliente (
    id_cliente      SERIAL        CONSTRAINT pk_cliente PRIMARY KEY,
    id_usuario      INT           NOT NULL CONSTRAINT uq_cliente_usuario UNIQUE,
    tipo_usuario    VARCHAR(10)   NOT NULL DEFAULT 'cliente' CONSTRAINT ck_cliente_tipo CHECK (tipo_usuario = 'cliente'),
    documento       VARCHAR(30)   NOT NULL CONSTRAINT uq_cliente_documento UNIQUE,
    telefono        VARCHAR(20),
    fecha_registro  DATE          NOT NULL DEFAULT CURRENT_DATE,
    CONSTRAINT fk_cliente_usuario FOREIGN KEY (id_usuario, tipo_usuario)
        REFERENCES usuario(id_usuario, tipo) ON DELETE CASCADE
);

CREATE TABLE empleado (
    id_empleado     SERIAL        CONSTRAINT pk_empleado PRIMARY KEY,
    id_usuario      INT           NOT NULL CONSTRAINT uq_empleado_usuario UNIQUE,
    tipo_usuario    VARCHAR(10)   NOT NULL DEFAULT 'empleado' CONSTRAINT ck_empleado_tipo_usuario CHECK (tipo_usuario = 'empleado'),
    tipo_empleado   VARCHAR(15)   NOT NULL CONSTRAINT ck_empleado_tipo CHECK (tipo_empleado IN ('administrativo','conductor')),
    id_punto_venta  INT           NOT NULL,
    documento       VARCHAR(30)   NOT NULL CONSTRAINT uq_empleado_documento UNIQUE,
    fecha_ingreso   DATE          NOT NULL,
    salario         NUMERIC(10,2) NOT NULL CONSTRAINT ck_empleado_salario CHECK (salario > 0),
    CONSTRAINT uq_empleado_id_tipo UNIQUE (id_empleado, tipo_empleado),
    CONSTRAINT fk_empleado_usuario FOREIGN KEY (id_usuario, tipo_usuario)
        REFERENCES usuario(id_usuario, tipo) ON DELETE CASCADE,
    CONSTRAINT fk_empleado_punto_venta FOREIGN KEY (id_punto_venta)
        REFERENCES punto_venta(id_punto_venta) ON DELETE RESTRICT
);

CREATE TABLE administrativo (
    id_empleado     INT           CONSTRAINT pk_administrativo PRIMARY KEY,
    tipo_empleado   VARCHAR(15)   NOT NULL DEFAULT 'administrativo' CONSTRAINT ck_administrativo_tipo CHECK (tipo_empleado = 'administrativo'),
    area            VARCHAR(100)  NOT NULL,
    nivel           VARCHAR(50),
    CONSTRAINT fk_administrativo_empleado FOREIGN KEY (id_empleado, tipo_empleado)
        REFERENCES empleado(id_empleado, tipo_empleado) ON DELETE CASCADE
);

CREATE TABLE conductor (
    id_empleado           INT          CONSTRAINT pk_conductor PRIMARY KEY,
    tipo_empleado         VARCHAR(15)  NOT NULL DEFAULT 'conductor' CONSTRAINT ck_conductor_tipo CHECK (tipo_empleado = 'conductor'),
    licencia              VARCHAR(30)  NOT NULL CONSTRAINT uq_conductor_licencia UNIQUE,
    categoria_licencia    VARCHAR(5)   NOT NULL CONSTRAINT ck_conductor_categoria CHECK (categoria_licencia IN ('A1','A2','B1','B2','C1','C2')),
    vencimiento_licencia  DATE         NOT NULL,
    CONSTRAINT fk_conductor_empleado FOREIGN KEY (id_empleado, tipo_empleado)
        REFERENCES empleado(id_empleado, tipo_empleado) ON DELETE CASCADE
);

CREATE TABLE direccion (
    id_direccion    SERIAL        CONSTRAINT pk_direccion PRIMARY KEY,
    id_cliente      INT           NOT NULL,
    direccion       VARCHAR(200)  NOT NULL,
    barrio          VARCHAR(100),
    referencia      VARCHAR(250),
    CONSTRAINT fk_direccion_cliente FOREIGN KEY (id_cliente) REFERENCES cliente(id_cliente) ON DELETE RESTRICT
);

CREATE TABLE vehiculo (
    id_vehiculo     SERIAL        CONSTRAINT pk_vehiculo PRIMARY KEY,
    id_punto_venta  INT           NOT NULL,
    placa           VARCHAR(20)   NOT NULL CONSTRAINT uq_vehiculo_placa UNIQUE,
    tipo            VARCHAR(20)   NOT NULL CONSTRAINT ck_vehiculo_tipo CHECK (tipo IN ('moto','furgoneta','camioneta')),
    capacidad_kg    NUMERIC(10,2) NOT NULL CONSTRAINT ck_vehiculo_capacidad CHECK (capacidad_kg > 0),
    estado          VARCHAR(20)   NOT NULL DEFAULT 'disponible'
                    CONSTRAINT ck_vehiculo_estado CHECK (estado IN ('disponible','en_ruta','mantenimiento')),
    CONSTRAINT fk_vehiculo_punto_venta FOREIGN KEY (id_punto_venta) REFERENCES punto_venta(id_punto_venta) ON DELETE RESTRICT
);

CREATE TABLE compra (
    id_compra       SERIAL        CONSTRAINT pk_compra PRIMARY KEY,
    id_cliente      INT           NOT NULL,
    id_punto_venta  INT           NOT NULL,
    fecha           TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    canal           VARCHAR(20)   NOT NULL CONSTRAINT ck_compra_canal CHECK (canal IN ('tienda','domicilio')),
    total           NUMERIC(12,2) NOT NULL DEFAULT 0 CONSTRAINT ck_compra_total CHECK (total >= 0),   -- derivado (trigger)
    CONSTRAINT fk_compra_cliente     FOREIGN KEY (id_cliente)     REFERENCES cliente(id_cliente)         ON DELETE RESTRICT,
    CONSTRAINT fk_compra_punto_venta FOREIGN KEY (id_punto_venta) REFERENCES punto_venta(id_punto_venta) ON DELETE RESTRICT
);

-- Cada línea registra la promoción que se le aplicó (0 o 1: las promociones no son acumulables)
-- y el descuento por unidad. precio_unitario = precio_lista - descuento es lo que paga el cliente.
CREATE TABLE detalle_compra (
    id_compra        INT           NOT NULL,
    id_producto      INT           NOT NULL,
    cantidad         INT           NOT NULL CONSTRAINT ck_detalle_compra_cantidad CHECK (cantidad > 0),
    precio_lista     NUMERIC(10,2) NOT NULL CONSTRAINT ck_detalle_compra_precio_lista CHECK (precio_lista >= 0),
    id_promocion     INT,                                                              -- NULL = sin promoción
    descuento        NUMERIC(10,2) NOT NULL DEFAULT 0,                                 -- por unidad, derivado (trigger)
    precio_unitario  NUMERIC(10,2) NOT NULL CONSTRAINT ck_detalle_compra_precio CHECK (precio_unitario >= 0),
    CONSTRAINT pk_detalle_compra PRIMARY KEY (id_compra, id_producto),
    CONSTRAINT ck_detalle_compra_descuento CHECK (descuento >= 0 AND descuento <= precio_lista),
    CONSTRAINT ck_detalle_compra_sin_promocion CHECK (id_promocion IS NOT NULL OR descuento = 0),
    CONSTRAINT ck_detalle_compra_precio_final CHECK (precio_unitario = precio_lista - descuento),
    CONSTRAINT fk_detalle_compra_compra   FOREIGN KEY (id_compra)   REFERENCES compra(id_compra)     ON DELETE CASCADE,
    CONSTRAINT fk_detalle_compra_producto FOREIGN KEY (id_producto) REFERENCES producto(id_producto) ON DELETE RESTRICT,
    -- La promoción aplicada debe cubrir el producto de la línea (misma columna id_producto).
    CONSTRAINT fk_detalle_compra_promocion FOREIGN KEY (id_promocion, id_producto)
        REFERENCES promocion_producto(id_promocion, id_producto) ON DELETE RESTRICT
);

-- El domicilio llega al cliente por un único camino: domicilio -> compra -> cliente.
-- La dirección de entrega se guarda como atributos del domicilio (copia tomada al hacer el
-- pedido desde la libreta de direcciones del cliente), no como FK a direccion.
CREATE TABLE domicilio (
    id_domicilio      SERIAL        CONSTRAINT pk_domicilio PRIMARY KEY,
    id_compra         INT           NOT NULL CONSTRAINT uq_domicilio_compra UNIQUE,   -- compra 1 : 0..1 domicilio
    direccion_entrega VARCHAR(200)  NOT NULL,
    barrio_entrega    VARCHAR(100),
    referencia        VARCHAR(250),
    id_vehiculo     INT,                                                             -- se asignan al despachar
    id_conductor    INT,
    estado          VARCHAR(20)   NOT NULL DEFAULT 'pendiente'
                    CONSTRAINT ck_domicilio_estado CHECK (estado IN ('pendiente','en_ruta','entregado','cancelado')),
    hora_entrega    TIMESTAMP,
    CONSTRAINT ck_domicilio_asignacion CHECK (
        estado IN ('pendiente','cancelado') OR (id_conductor IS NOT NULL AND id_vehiculo IS NOT NULL)),
    CONSTRAINT ck_domicilio_hora CHECK ((estado = 'entregado') = (hora_entrega IS NOT NULL)),
    CONSTRAINT fk_domicilio_compra    FOREIGN KEY (id_compra)    REFERENCES compra(id_compra)       ON DELETE RESTRICT,
    CONSTRAINT fk_domicilio_vehiculo  FOREIGN KEY (id_vehiculo)  REFERENCES vehiculo(id_vehiculo)   ON DELETE RESTRICT,
    CONSTRAINT fk_domicilio_conductor FOREIGN KEY (id_conductor) REFERENCES conductor(id_empleado)  ON DELETE RESTRICT
);



CREATE TABLE documento (
    id_doc           SERIAL        CONSTRAINT pk_documento PRIMARY KEY,
    id_producto      INT,                                    -- solo las fichas describen un producto
    codigo_doc       VARCHAR(60)   NOT NULL CONSTRAINT uq_documento_codigo UNIQUE,
    tipo             VARCHAR(20)   NOT NULL
                     CONSTRAINT ck_documento_tipo CHECK (tipo IN ('ficha','politica','manual','guia')),
    titulo           VARCHAR(200)  NOT NULL,
    idioma           CHAR(2)       NOT NULL DEFAULT 'es' CONSTRAINT ck_documento_idioma CHECK (idioma IN ('es','en')),
    fecha            DATE,
    fuente           VARCHAR(255)  NOT NULL,
    contenido_texto  TEXT          NOT NULL,
    CONSTRAINT ck_documento_ficha CHECK ((tipo = 'ficha') = (id_producto IS NOT NULL)),
    CONSTRAINT fk_documento_producto FOREIGN KEY (id_producto) REFERENCES producto(id_producto) ON DELETE RESTRICT
);

-- Imagen tiene un único dueño: el documento (la ficha) que la contiene.
-- El producto que muestra se obtiene por imagen -> documento -> producto.
CREATE TABLE imagen (
    id_img           SERIAL        CONSTRAINT pk_imagen PRIMARY KEY,
    id_doc           INT           NOT NULL,
    codigo_img       VARCHAR(60)   NOT NULL CONSTRAINT uq_imagen_codigo UNIQUE,
    ruta_archivo     TEXT          NOT NULL,
    sha256           CHAR(64)      NOT NULL CONSTRAINT uq_imagen_sha256 UNIQUE,   -- la misma foto no se duplica
    ancho            INT           CONSTRAINT ck_imagen_ancho CHECK (ancho > 0),
    alto             INT           CONSTRAINT ck_imagen_alto  CHECK (alto > 0),
    descripcion      VARCHAR(200),                          -- corta: el codificador de texto de CLIP trunca
    CONSTRAINT fk_imagen_documento FOREIGN KEY (id_doc) REFERENCES documento(id_doc) ON DELETE CASCADE
);

-- Etiquetas: catálogo único + tabla asociativa (N:M)
CREATE TABLE etiqueta (
    id_etiqueta      SERIAL        CONSTRAINT pk_etiqueta PRIMARY KEY,
    nombre           VARCHAR(50)   NOT NULL CONSTRAINT uq_etiqueta_nombre UNIQUE
);

CREATE TABLE imagen_etiqueta (
    id_img           INT NOT NULL,
    id_etiqueta      INT NOT NULL,
    CONSTRAINT pk_imagen_etiqueta PRIMARY KEY (id_img, id_etiqueta),
    CONSTRAINT fk_imagen_etiqueta_imagen   FOREIGN KEY (id_img)      REFERENCES imagen(id_img)        ON DELETE CASCADE,
    CONSTRAINT fk_imagen_etiqueta_etiqueta FOREIGN KEY (id_etiqueta) REFERENCES etiqueta(id_etiqueta) ON DELETE RESTRICT
);

-- Conjunto de evaluación: preguntas con respuesta de referencia (ground truth), redactadas
-- ANTES del experimento (data/evaluacion/preguntas.csv), y los documentos que las responden.
CREATE TABLE pregunta (
    id_pregunta      SERIAL        CONSTRAINT pk_pregunta PRIMARY KEY,
    codigo_pregunta  VARCHAR(10)   NOT NULL CONSTRAINT uq_pregunta_codigo UNIQUE,
    texto_pregunta   TEXT          NOT NULL CONSTRAINT uq_pregunta_texto UNIQUE,
    ground_truth     TEXT          NOT NULL,
    tipo             VARCHAR(16)   NOT NULL
                     CONSTRAINT ck_pregunta_tipo CHECK (tipo IN ('ficha','politica','manual','guia','multidocumento')),
    fecha_creacion   DATE          NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE pregunta_documento (
    id_pregunta      INT NOT NULL,
    id_doc           INT NOT NULL,
    CONSTRAINT pk_pregunta_documento PRIMARY KEY (id_pregunta, id_doc),
    CONSTRAINT fk_pregunta_documento_pregunta  FOREIGN KEY (id_pregunta) REFERENCES pregunta(id_pregunta) ON DELETE CASCADE,
    CONSTRAINT fk_pregunta_documento_documento FOREIGN KEY (id_doc)      REFERENCES documento(id_doc)     ON DELETE RESTRICT
);

CREATE TABLE consulta (
    id_consulta             SERIAL        CONSTRAINT pk_consulta PRIMARY KEY,
    id_usuario              INT           NOT NULL,
    id_pregunta             INT,                    -- solo en las corridas del experimento
    texto_pregunta          TEXT,                   -- solo en consultas libres (si hay pregunta, el texto está allá)
    ruta_imagen_consulta    TEXT,                   -- solo en consultas que parten de una foto
    tipo_consulta           VARCHAR(20)   NOT NULL
                            CONSTRAINT ck_consulta_tipo CHECK (tipo_consulta IN ('texto_texto','texto_imagen','imagen_imagen',
                                                                                 'imagen_texto','hibrida','rag')),
    estrategia_chunking     VARCHAR(20)
                            CONSTRAINT ck_consulta_estrategia CHECK (estrategia_chunking IN ('fijo','oraciones','semantico')),
    top_k                   SMALLINT      NOT NULL DEFAULT 5 CONSTRAINT ck_consulta_top_k CHECK (top_k BETWEEN 1 AND 50),
    respuesta_llm           TEXT,
    modelo_llm              VARCHAR(100),
    tiempo_recuperacion_ms  NUMERIC(10,2) CONSTRAINT ck_consulta_t_recuperacion CHECK (tiempo_recuperacion_ms >= 0),
    tiempo_total_ms         NUMERIC(10,2) CONSTRAINT ck_consulta_t_total CHECK (tiempo_total_ms >= 0),
    fecha                   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- la entrada es una foto, o bien un texto que vive en un solo lugar (pregunta o texto libre)
    CONSTRAINT ck_consulta_entrada CHECK (
        (tipo_consulta IN ('imagen_imagen','imagen_texto')
             AND ruta_imagen_consulta IS NOT NULL AND id_pregunta IS NULL AND texto_pregunta IS NULL)
        OR
        (tipo_consulta NOT IN ('imagen_imagen','imagen_texto')
             AND ruta_imagen_consulta IS NULL AND num_nonnulls(id_pregunta, texto_pregunta) = 1)),
    -- la estrategia aplica cuando se recuperan chunks y no aplica cuando solo se recuperan imágenes
    CONSTRAINT ck_consulta_estrategia_tipo CHECK (
        (tipo_consulta IN ('texto_imagen','imagen_imagen')) = (estrategia_chunking IS NULL)),
    -- las corridas del experimento son RAG completo (recuperar + generar)
    CONSTRAINT ck_consulta_pregunta_rag CHECK (id_pregunta IS NULL OR tipo_consulta = 'rag'),
    CONSTRAINT ck_consulta_tiempos CHECK (tiempo_total_ms IS NULL OR tiempo_recuperacion_ms IS NULL
                                          OR tiempo_total_ms >= tiempo_recuperacion_ms),
    CONSTRAINT ck_consulta_modelo_llm CHECK (respuesta_llm IS NULL OR modelo_llm IS NOT NULL),
    -- una corrida por pregunta y estrategia
    CONSTRAINT uq_consulta_pregunta_estrategia UNIQUE (id_pregunta, estrategia_chunking),
    CONSTRAINT fk_consulta_usuario  FOREIGN KEY (id_usuario)  REFERENCES usuario(id_usuario)   ON DELETE RESTRICT,
    CONSTRAINT fk_consulta_pregunta FOREIGN KEY (id_pregunta) REFERENCES pregunta(id_pregunta) ON DELETE RESTRICT
);


CREATE TABLE embeddings_texto (
    id_embedding         SERIAL        CONSTRAINT pk_embeddings_texto PRIMARY KEY,
    id_doc               INT           NOT NULL,
    chunk_id             INT           NOT NULL CONSTRAINT ck_embeddings_texto_chunk_id CHECK (chunk_id >= 0),
    estrategia_chunking  VARCHAR(20)   NOT NULL
                         CONSTRAINT ck_embeddings_texto_estrategia CHECK (estrategia_chunking IN ('fijo','oraciones','semantico')),
    contenido_chunk      TEXT          NOT NULL,
    -- tokens de lo que realmente lee el modelo ("passage: " + título + chunk): nunca más de 512,
    -- así ningún chunk se trunca al vectorizar
    n_tokens             SMALLINT      NOT NULL CONSTRAINT ck_embeddings_texto_tokens CHECK (n_tokens BETWEEN 1 AND 512),
    parametros           JSONB         NOT NULL,
    vector_embedding     VECTOR(384)   NOT NULL,
    modelo               VARCHAR(100)  NOT NULL,
    CONSTRAINT uq_embeddings_texto_chunk UNIQUE (id_doc, estrategia_chunking, chunk_id),
    CONSTRAINT fk_embeddings_texto_documento FOREIGN KEY (id_doc) REFERENCES documento(id_doc) ON DELETE CASCADE
);

-- El mismo chunk en el espacio CLIP (512), solo para la ruta exploratoria imagen -> texto.
-- 1:1 con embeddings_texto (su PK es la FK).
CREATE TABLE embeddings_texto_clip (
    id_embedding         INT           CONSTRAINT pk_embeddings_texto_clip PRIMARY KEY,
    vector_embedding     VECTOR(512)   NOT NULL,
    modelo               VARCHAR(100)  NOT NULL,
    CONSTRAINT fk_embeddings_texto_clip_chunk FOREIGN KEY (id_embedding)
        REFERENCES embeddings_texto(id_embedding) ON DELETE CASCADE
);

CREATE TABLE embeddings_imagen (
    id_embedding         SERIAL        CONSTRAINT pk_embeddings_imagen PRIMARY KEY,
    id_img               INT           NOT NULL CONSTRAINT uq_embeddings_imagen_img UNIQUE,   -- 1:1 con imagen
    vector_embedding     VECTOR(512)   NOT NULL,                                               -- píxeles (PIL + CLIP)
    modelo               VARCHAR(100)  NOT NULL,
    vector_descripcion   VECTOR(512),                                                          -- descripción + etiquetas
    modelo_descripcion   VARCHAR(100),
    CONSTRAINT ck_embeddings_imagen_desc CHECK ((vector_descripcion IS NULL) = (modelo_descripcion IS NULL)),
    CONSTRAINT fk_embeddings_imagen_imagen FOREIGN KEY (id_img) REFERENCES imagen(id_img) ON DELETE CASCADE
);

CREATE TABLE query_embeddings (
    id_qemb              SERIAL        CONSTRAINT pk_query_embeddings PRIMARY KEY,
    id_consulta          INT           NOT NULL CONSTRAINT uq_query_embeddings_consulta UNIQUE,   -- 1:1 con consulta
    vector_texto         VECTOR(384),          -- e5 ("query: "): se compara con embeddings_texto
    modelo_texto         VARCHAR(100),
    vector_clip          VECTOR(512),          -- CLIP (texto o foto): se compara con embeddings_imagen
    modelo_clip          VARCHAR(100),
    CONSTRAINT ck_query_embeddings_alguno     CHECK (num_nonnulls(vector_texto, vector_clip) >= 1),
    CONSTRAINT ck_query_embeddings_modelo_txt CHECK ((vector_texto IS NULL) = (modelo_texto IS NULL)),
    CONSTRAINT ck_query_embeddings_modelo_clp CHECK ((vector_clip  IS NULL) = (modelo_clip  IS NULL)),
    CONSTRAINT fk_query_embeddings_consulta FOREIGN KEY (id_consulta) REFERENCES consulta(id_consulta) ON DELETE CASCADE
);

-- Resultado apunta al CHUNK recuperado (no al documento) o a la imagen, nunca a ambos.
CREATE TABLE resultado (
    id_resultado     SERIAL        CONSTRAINT pk_resultado PRIMARY KEY,
    id_consulta      INT           NOT NULL,
    id_chunk         INT,                      -- -> embeddings_texto (trae documento y estrategia)
    id_img           INT,
    posicion         SMALLINT      NOT NULL CONSTRAINT ck_resultado_posicion CHECK (posicion >= 1),
    score_similitud  NUMERIC(9,6)  NOT NULL CONSTRAINT ck_resultado_score CHECK (score_similitud BETWEEN -1 AND 1),
    CONSTRAINT ck_resultado_exclusivo CHECK (num_nonnulls(id_chunk, id_img) = 1),
    CONSTRAINT uq_resultado_posicion  UNIQUE (id_consulta, posicion),
    CONSTRAINT uq_resultado_chunk     UNIQUE (id_consulta, id_chunk),
    CONSTRAINT uq_resultado_img       UNIQUE (id_consulta, id_img),
    CONSTRAINT fk_resultado_consulta FOREIGN KEY (id_consulta) REFERENCES consulta(id_consulta)          ON DELETE CASCADE,
    CONSTRAINT fk_resultado_chunk    FOREIGN KEY (id_chunk)    REFERENCES embeddings_texto(id_embedding) ON DELETE RESTRICT,
    CONSTRAINT fk_resultado_imagen   FOREIGN KEY (id_img)      REFERENCES imagen(id_img)                 ON DELETE RESTRICT
);

CREATE TABLE evaluacion (
    id_eval            SERIAL        CONSTRAINT pk_evaluacion PRIMARY KEY,
    id_consulta        INT           NOT NULL CONSTRAINT uq_evaluacion_consulta UNIQUE,   -- 1:1
    faithfulness       NUMERIC(4,3)  NOT NULL CONSTRAINT ck_evaluacion_faithfulness     CHECK (faithfulness     BETWEEN 0 AND 1),
    answer_relevancy   NUMERIC(4,3)  NOT NULL CONSTRAINT ck_evaluacion_answer_relevancy CHECK (answer_relevancy BETWEEN 0 AND 1),
    context_recall     NUMERIC(4,3)  NOT NULL CONSTRAINT ck_evaluacion_context_recall   CHECK (context_recall   BETWEEN 0 AND 1),
    modelo_eval        VARCHAR(100)  NOT NULL,
    fecha              TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_evaluacion_consulta FOREIGN KEY (id_consulta) REFERENCES consulta(id_consulta) ON DELETE CASCADE
);


-- E1. compra.total es derivado: suma de cantidad * precio_unitario de sus líneas.
CREATE FUNCTION fn_actualizar_total_compra() RETURNS trigger AS $$
BEGIN
    UPDATE compra c
       SET total = COALESCE((SELECT SUM(d.cantidad * d.precio_unitario)
                               FROM detalle_compra d WHERE d.id_compra = c.id_compra), 0)
     WHERE c.id_compra = COALESCE(NEW.id_compra, OLD.id_compra);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_detalle_compra_total
    AFTER INSERT OR UPDATE OR DELETE ON detalle_compra
    FOR EACH ROW EXECUTE FUNCTION fn_actualizar_total_compra();

-- E2. Un resultado de texto viene de un chunk de la MISMA estrategia de la consulta, y cada
--     tipo de consulta solo admite el tipo de recurso que recupera.
CREATE FUNCTION fn_validar_resultado() RETURNS trigger AS $$
DECLARE
    v_estrategia_consulta VARCHAR(20);
    v_tipo                VARCHAR(20);
    v_estrategia_chunk    VARCHAR(20);
BEGIN
    SELECT estrategia_chunking, tipo_consulta INTO v_estrategia_consulta, v_tipo
      FROM consulta WHERE id_consulta = NEW.id_consulta;

    IF NEW.id_chunk IS NOT NULL THEN
        IF v_tipo NOT IN ('texto_texto','imagen_texto','hibrida','rag') THEN
            RAISE EXCEPTION 'La consulta % es de tipo % y no admite chunks como resultado', NEW.id_consulta, v_tipo;
        END IF;
        SELECT estrategia_chunking INTO v_estrategia_chunk
          FROM embeddings_texto WHERE id_embedding = NEW.id_chunk;
        IF v_estrategia_chunk IS DISTINCT FROM v_estrategia_consulta THEN
            RAISE EXCEPTION 'El chunk % es de la estrategia %, pero la consulta % usa %',
                NEW.id_chunk, v_estrategia_chunk, NEW.id_consulta, v_estrategia_consulta;
        END IF;
    ELSIF v_tipo NOT IN ('texto_imagen','imagen_imagen','rag') THEN
        RAISE EXCEPTION 'La consulta % es de tipo % y no admite imágenes como resultado', NEW.id_consulta, v_tipo;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validar_resultado
    BEFORE INSERT OR UPDATE ON resultado
    FOR EACH ROW EXECUTE FUNCTION fn_validar_resultado();

-- E3. Solo se evalúa con RAGAS una corrida del experimento: tiene pregunta (ground truth) y respuesta.
CREATE FUNCTION fn_validar_evaluacion() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM consulta
                    WHERE id_consulta = NEW.id_consulta
                      AND id_pregunta IS NOT NULL
                      AND respuesta_llm IS NOT NULL) THEN
        RAISE EXCEPTION 'La consulta % no tiene pregunta con ground_truth o respuesta del LLM; no se puede evaluar',
            NEW.id_consulta;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validar_evaluacion
    BEFORE INSERT OR UPDATE ON evaluacion
    FOR EACH ROW EXECUTE FUNCTION fn_validar_evaluacion();

-- E4. La promoción de una línea debe estar vigente en la fecha de la compra; el descuento por
--     unidad y el precio final se derivan de ella (porcentaje del precio de lista o valor fijo,
--     sin bajar de 0). Que la promoción cubra el producto lo garantiza fk_detalle_compra_promocion.
CREATE FUNCTION fn_aplicar_promocion() RETURNS trigger AS $$
DECLARE
    v_tipo   VARCHAR(20);
    v_valor  NUMERIC(10,2);
    v_inicio DATE;
    v_fin    DATE;
    v_fecha  DATE;
BEGIN
    IF NEW.id_promocion IS NULL THEN
        NEW.descuento := 0;
    ELSE
        SELECT tipo_descuento, valor, fecha_inicio, fecha_fin INTO v_tipo, v_valor, v_inicio, v_fin
          FROM promocion WHERE id_promocion = NEW.id_promocion;
        SELECT fecha::date INTO v_fecha FROM compra WHERE id_compra = NEW.id_compra;
        IF v_fecha NOT BETWEEN v_inicio AND v_fin THEN
            RAISE EXCEPTION 'La promoción % no está vigente el % (vigencia % a %)',
                NEW.id_promocion, v_fecha, v_inicio, v_fin;
        END IF;
        NEW.descuento := CASE v_tipo
                             WHEN 'porcentaje' THEN round(NEW.precio_lista * v_valor / 100, 2)
                             ELSE LEAST(v_valor, NEW.precio_lista)
                         END;
    END IF;
    NEW.precio_unitario := NEW.precio_lista - NEW.descuento;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_aplicar_promocion
    BEFORE INSERT OR UPDATE OF id_compra, id_promocion, precio_lista ON detalle_compra
    FOR EACH ROW EXECUTE FUNCTION fn_aplicar_promocion();


CREATE FUNCTION fn_validar_isa_usuario() RETURNS trigger AS $$
BEGIN
    IF (NEW.tipo = 'cliente'  AND NOT EXISTS (SELECT 1 FROM cliente  WHERE id_usuario = NEW.id_usuario))
    OR (NEW.tipo = 'empleado' AND NOT EXISTS (SELECT 1 FROM empleado WHERE id_usuario = NEW.id_usuario)) THEN
        RAISE EXCEPTION 'El usuario % es de tipo % pero no tiene fila en esa tabla', NEW.id_usuario, NEW.tipo;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER trg_isa_usuario
    AFTER INSERT OR UPDATE ON usuario
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION fn_validar_isa_usuario();

CREATE FUNCTION fn_validar_isa_empleado() RETURNS trigger AS $$
BEGIN
    IF (NEW.tipo_empleado = 'administrativo' AND NOT EXISTS (SELECT 1 FROM administrativo WHERE id_empleado = NEW.id_empleado))
    OR (NEW.tipo_empleado = 'conductor'      AND NOT EXISTS (SELECT 1 FROM conductor      WHERE id_empleado = NEW.id_empleado)) THEN
        RAISE EXCEPTION 'El empleado % es % pero no tiene fila en esa tabla', NEW.id_empleado, NEW.tipo_empleado;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER trg_isa_empleado
    AFTER INSERT OR UPDATE ON empleado
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION fn_validar_isa_empleado();



CREATE INDEX idx_producto_categoria           ON producto (id_categoria);
CREATE INDEX idx_producto_marca               ON producto (id_marca);
CREATE INDEX idx_producto_proveedor           ON producto (id_proveedor);
CREATE INDEX idx_inventario_producto          ON inventario (id_producto);
CREATE INDEX idx_promocion_producto_producto  ON promocion_producto (id_producto);
CREATE INDEX idx_empleado_punto_venta         ON empleado (id_punto_venta);
CREATE INDEX idx_direccion_cliente            ON direccion (id_cliente);
CREATE INDEX idx_vehiculo_punto_venta         ON vehiculo (id_punto_venta);
CREATE INDEX idx_compra_cliente               ON compra (id_cliente);
CREATE INDEX idx_compra_punto_venta           ON compra (id_punto_venta);
CREATE INDEX idx_detalle_compra_producto      ON detalle_compra (id_producto);
CREATE INDEX idx_detalle_compra_promocion     ON detalle_compra (id_promocion) WHERE id_promocion IS NOT NULL;
CREATE INDEX idx_domicilio_vehiculo           ON domicilio (id_vehiculo);
CREATE INDEX idx_domicilio_conductor          ON domicilio (id_conductor);
CREATE INDEX idx_documento_producto           ON documento (id_producto);
CREATE INDEX idx_imagen_documento             ON imagen (id_doc);
CREATE INDEX idx_imagen_etiqueta_etiqueta     ON imagen_etiqueta (id_etiqueta);
CREATE INDEX idx_pregunta_documento_doc       ON pregunta_documento (id_doc);
CREATE INDEX idx_consulta_usuario             ON consulta (id_usuario);
CREATE INDEX idx_consulta_pregunta            ON consulta (id_pregunta);
CREATE INDEX idx_resultado_chunk              ON resultado (id_chunk);
CREATE INDEX idx_resultado_imagen             ON resultado (id_img);


CREATE INDEX idx_producto_precio              ON producto (precio);
CREATE INDEX idx_inventario_disponible        ON inventario (id_punto_venta, id_producto) WHERE stock > 0;
CREATE INDEX idx_documento_tipo_idioma        ON documento (tipo, idioma);
CREATE INDEX idx_consulta_estrategia          ON consulta (estrategia_chunking);
-- Texto completo en español sobre los chunks (busqueda.buscar_texto_texto). La expresión
-- debe ser idéntica a la de la consulta para que el índice se use.
CREATE INDEX idx_emb_texto_fts ON embeddings_texto USING gin (to_tsvector('spanish', contenido_chunk));


CREATE INDEX idx_emb_texto_hnsw_fijo ON embeddings_texto
    USING hnsw (vector_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
    WHERE estrategia_chunking = 'fijo';
CREATE INDEX idx_emb_texto_hnsw_oraciones ON embeddings_texto
    USING hnsw (vector_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
    WHERE estrategia_chunking = 'oraciones';
CREATE INDEX idx_emb_texto_hnsw_semantico ON embeddings_texto
    USING hnsw (vector_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
    WHERE estrategia_chunking = 'semantico';
CREATE INDEX idx_emb_imagen_hnsw ON embeddings_imagen
    USING hnsw (vector_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_emb_imagen_desc_hnsw ON embeddings_imagen
    USING hnsw (vector_descripcion vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_emb_texto_clip_hnsw ON embeddings_texto_clip
    USING hnsw (vector_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);


CREATE VIEW v_resultados_experimento AS
WITH primer_acierto AS (
    SELECT r.id_consulta, MIN(r.posicion) AS posicion
      FROM resultado r
      JOIN consulta c            ON c.id_consulta = r.id_consulta
      JOIN embeddings_texto e    ON e.id_embedding = r.id_chunk
      JOIN pregunta_documento pd ON pd.id_pregunta = c.id_pregunta AND pd.id_doc = e.id_doc
     GROUP BY r.id_consulta
)
SELECT c.id_consulta,
       p.id_pregunta,
       p.codigo_pregunta,
       p.tipo                                         AS tipo_pregunta,
       c.estrategia_chunking,
       c.top_k,
       pa.posicion                                    AS posicion_primer_acierto,
       COALESCE((pa.posicion = 1)::int, 0)            AS hit_1,
       (pa.posicion IS NOT NULL)::int                 AS hit_k,
       COALESCE(round(1.0 / pa.posicion, 4), 0)       AS reciprocal_rank,
       c.tiempo_recuperacion_ms,
       c.tiempo_total_ms,
       ev.faithfulness,
       ev.answer_relevancy,
       ev.context_recall
  FROM consulta c
  JOIN pregunta p              ON p.id_pregunta = c.id_pregunta
  LEFT JOIN primer_acierto pa  ON pa.id_consulta = c.id_consulta
  LEFT JOIN evaluacion ev      ON ev.id_consulta = c.id_consulta;

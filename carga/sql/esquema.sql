-- carga/sql/esquema.sql
-- Esquema de la base de datos de Nexus Dominio (PostgreSQL 16).
--
-- Es IDEMPOTENTE: se puede ejecutar todas las veces que se quiera. Cada objeto
-- se crea solo si no existe, y nunca se borra ni se modifica nada existente.
--
-- Solo el cargador (servicio "carga") ejecuta este archivo. Las réplicas de
-- Dominio NO crean tablas: así dos réplicas que arrancan a la vez no compiten.
--
-- Criterio de diseño: solo las claves y los campos que la lógica necesita son
-- obligatorios (NOT NULL). Los datos opcionales admiten NULL y la lógica de
-- negocio los trata de forma conservadora (por ejemplo, stock desconocido
-- cuenta como "sin stock" y consentimiento desconocido cuenta como "sin consentimiento").

-- ---------------------------------------------------------------------------
-- Datos de referencia (los llena el cargador desde los CSV tratados)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS productos (
    sku               TEXT PRIMARY KEY,
    nombre            TEXT,
    categoria         TEXT,
    marca             TEXT,
    precio_lista      NUMERIC(12, 2),
    stock             INTEGER,            -- puede ser negativo en el origen
    activo            BOOLEAN,
    fecha_alta        DATE,
    precio_sospechoso BOOLEAN,
    recomendable      BOOLEAN
);

CREATE INDEX IF NOT EXISTS idx_productos_categoria ON productos (categoria);

-- Solo se cargan las columnas que Dominio usa. No se cargan "edad" ni
-- "email_valido": ninguna regla las necesita (minimización de datos).
CREATE TABLE IF NOT EXISTS usuarios (
    usuario_id       TEXT PRIMARY KEY,
    fecha_registro   DATE,
    region           TEXT,
    canal_captacion  TEXT,
    acepta_marketing BOOLEAN,
    consentimiento   BOOLEAN
);

CREATE TABLE IF NOT EXISTS transacciones (
    pedido_id       TEXT      NOT NULL,
    linea           SMALLINT  NOT NULL,
    usuario_id      TEXT      NOT NULL REFERENCES usuarios (usuario_id),
    sku             TEXT      NOT NULL REFERENCES productos (sku),
    fecha           TIMESTAMP NOT NULL,   -- hora local del origen, sin zona horaria
    cantidad        INTEGER   NOT NULL CHECK (cantidad > 0),
    precio_unitario NUMERIC(12, 2),
    descuento       NUMERIC(12, 2),
    monto           NUMERIC(14, 2),
    canal           TEXT,
    estado          TEXT      NOT NULL CHECK (estado IN ('pagado', 'devuelto')),
    PRIMARY KEY (pedido_id, linea)
);

CREATE INDEX IF NOT EXISTS idx_transacciones_usuario_fecha ON transacciones (usuario_id, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_transacciones_sku           ON transacciones (sku);
CREATE INDEX IF NOT EXISTS idx_transacciones_fecha         ON transacciones (fecha);

-- ---------------------------------------------------------------------------
-- Datos que genera Dominio en operación
-- ---------------------------------------------------------------------------

-- Clientes que pidieron que no se use su historial (RF11, RN2). Si un usuario
-- aparece aquí, Dominio no llama a IA y responde con el respaldo general.
CREATE TABLE IF NOT EXISTS exclusiones_perfilamiento (
    usuario_id    TEXT        PRIMARY KEY REFERENCES usuarios (usuario_id),
    solicitado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Cada predicción que atiende Dominio: su entrada, su resultado, la versión
-- del modelo y la fecha. No lleva clave foránea a "usuarios" porque también se
-- registran consultas de usuarios desconocidos (arranque en frío, RF8).
CREATE TABLE IF NOT EXISTS predicciones (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id     TEXT        NOT NULL,
    k              SMALLINT    NOT NULL CHECK (k BETWEEN 4 AND 8),
    origen         TEXT        NOT NULL CHECK (origen IN ('modelo', 'fallback')),
    motivo         TEXT,
    version_modelo TEXT        NOT NULL,
    entrada        JSONB       NOT NULL,  -- el cuerpo recibido en la solicitud
    resultado      JSONB       NOT NULL,  -- la lista de recomendaciones entregada
    ia_ms          INTEGER,               -- tiempo de la llamada a IA (NULL si no se llamó)
    total_ms       INTEGER,
    atendido_por   TEXT        NOT NULL,  -- hostname de la réplica que respondió
    creado_en      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_predicciones_usuario ON predicciones (usuario_id, creado_en DESC);

-- ---------------------------------------------------------------------------
-- Registro de cada ejecución del cargador (evidencia de idempotencia)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS auditoria_carga (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ejecutado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
    tabla               TEXT        NOT NULL,
    archivo             TEXT        NOT NULL,
    archivo_sha256      TEXT        NOT NULL,
    filas_archivo       INTEGER     NOT NULL,  -- filas de datos del CSV
    filas_insertadas    INTEGER     NOT NULL,  -- nuevas en esta ejecución
    filas_ya_existentes INTEGER     NOT NULL,  -- ya estaban (no se duplican)
    filas_descartadas   INTEGER     NOT NULL,  -- no cumplían las claves indispensables
    detalle             TEXT
);
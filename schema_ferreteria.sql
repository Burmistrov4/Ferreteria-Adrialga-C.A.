-- ============================================================
-- ESQUEMA DDL — SISTEMA ERP / POS FERRETERÍA ADRIALGA, C.A.
-- Motor: PostgreSQL 16+
-- Uso: Importar en drawDB y/o inicializar base de datos
-- ============================================================

-- ============================================================
-- 1. MÓDULO DE SEGURIDAD, cPANEL Y RBAC
-- ============================================================

CREATE TABLE roles (
    id          SERIAL PRIMARY KEY,
    nombre      VARCHAR(50)  NOT NULL UNIQUE,
    descripcion TEXT
);

CREATE TABLE modulos (
    id     SERIAL PRIMARY KEY,
    codigo VARCHAR(50)  NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL
);

CREATE TABLE permisos (
    id     SERIAL PRIMARY KEY,
    accion VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE rol_permisos (
    rol_id     INTEGER NOT NULL,
    modulo_id  INTEGER NOT NULL,
    permiso_id INTEGER NOT NULL,
    PRIMARY KEY (rol_id, modulo_id, permiso_id),
    CONSTRAINT fk_rol_permisos_rol
        FOREIGN KEY (rol_id) REFERENCES roles (id) ON DELETE CASCADE,
    CONSTRAINT fk_rol_permisos_modulo
        FOREIGN KEY (modulo_id) REFERENCES modulos (id) ON DELETE CASCADE,
    CONSTRAINT fk_rol_permisos_permiso
        FOREIGN KEY (permiso_id) REFERENCES permisos (id) ON DELETE CASCADE
);

CREATE TABLE usuarios (
    id             SERIAL PRIMARY KEY,
    nombre_completo VARCHAR(120) NOT NULL,
    username       VARCHAR(50)  NOT NULL UNIQUE,
    email          VARCHAR(120) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    rol_id         INTEGER      NOT NULL,
    activo         BOOLEAN      NOT NULL DEFAULT TRUE,
    es_superuser   BOOLEAN      NOT NULL DEFAULT FALSE,
    fecha_creacion TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_usuarios_rol
        FOREIGN KEY (rol_id) REFERENCES roles (id)
);

CREATE TABLE sesiones_usuario (
    id               VARCHAR(64) PRIMARY KEY,
    usuario_id       INTEGER     NOT NULL,
    ip_address       VARCHAR(45),
    user_agent       VARCHAR(255),
    fecha_inicio     TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_expiracion TIMESTAMP   NOT NULL,
    activa           BOOLEAN     NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_sesiones_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE
);

CREATE TABLE bitacora_auditoria (
    id         BIGSERIAL PRIMARY KEY,
    usuario_id INTEGER,
    accion     VARCHAR(100) NOT NULL,
    modulo     VARCHAR(100) NOT NULL,
    detalles   TEXT,
    ip_address VARCHAR(45),
    fecha      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_bitacora_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE SET NULL
);

-- ============================================================
-- 2. MÓDULO DE INVENTARIO Y CONFIGURACIÓN FISCAL
-- ============================================================

CREATE TABLE categorias (
    id          SERIAL PRIMARY KEY,
    nombre      VARCHAR(80) NOT NULL UNIQUE,
    descripcion TEXT
);

-- Alícuotas: G 16%, R 8%, A 31%, E 0%
CREATE TABLE configuracion_fiscal (
    id          SERIAL PRIMARY KEY,
    codigo      VARCHAR(5)   NOT NULL UNIQUE,
    porcentaje  DECIMAL(5,2) NOT NULL CHECK (porcentaje IN (0, 8, 16, 31)),
    descripcion VARCHAR(100) NOT NULL
);

CREATE TABLE productos (
    id            SERIAL PRIMARY KEY,
    codigo_barras VARCHAR(30)   NOT NULL UNIQUE,
    descripcion   VARCHAR(150)  NOT NULL,
    categoria_id  INTEGER       NOT NULL,
    alicuota_id   INTEGER       NOT NULL,
    precio_ref    DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (precio_ref >= 0),
    stock_actual  DECIMAL(12,3) NOT NULL DEFAULT 0 CHECK (stock_actual >= 0),
    stock_minimo  DECIMAL(12,3) NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
    activo        BOOLEAN       NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_productos_categoria
        FOREIGN KEY (categoria_id) REFERENCES categorias (id),
    CONSTRAINT fk_productos_alicuota
        FOREIGN KEY (alicuota_id) REFERENCES configuracion_fiscal (id)
);

CREATE TABLE kardex_movimientos (
    id             BIGSERIAL PRIMARY KEY,
    producto_id    INTEGER       NOT NULL,
    tipo_movimiento VARCHAR(10)  NOT NULL CHECK (tipo_movimiento IN ('ENTRADA', 'SALIDA', 'AJUSTE')),
    cantidad       DECIMAL(12,3) NOT NULL CHECK (cantidad <> 0),
    costo_ref      DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (costo_ref >= 0),
    origen_id      INTEGER,
    fecha          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_kardex_producto
        FOREIGN KEY (producto_id) REFERENCES productos (id)
);

-- ============================================================
-- 3. MÓDULO DE VENTAS, POS Y MULTIMONEDA
-- ============================================================

CREATE TABLE clientes (
    id          SERIAL PRIMARY KEY,
    cedula_rif  VARCHAR(12)  NOT NULL UNIQUE,
    razon_social VARCHAR(150) NOT NULL,
    direccion   TEXT,
    telefono    VARCHAR(20),
    email       VARCHAR(120)
);

-- Tasa REF / BCV diaria
CREATE TABLE tasas_ref (
    id       SERIAL PRIMARY KEY,
    fecha    TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    monto_bs DECIMAL(12,4)  NOT NULL CHECK (monto_bs > 0),
    origen   VARCHAR(30)    NOT NULL DEFAULT 'BCV'
);

CREATE TABLE correlativos_fiscales (
    id            SERIAL PRIMARY KEY,
    tipo_documento VARCHAR(20) NOT NULL,
    serie         VARCHAR(10)  NOT NULL,
    ultimo_numero INTEGER      NOT NULL DEFAULT 0 CHECK (ultimo_numero >= 0),
    UNIQUE (tipo_documento, serie)
);

CREATE TABLE facturas (
    id             BIGSERIAL PRIMARY KEY,
    numero_factura VARCHAR(30)   NOT NULL UNIQUE,
    correlativo    INTEGER       NOT NULL,
    cliente_id     INTEGER       NOT NULL,
    usuario_id     INTEGER       NOT NULL,
    tasa_ref_monto DECIMAL(12,4) NOT NULL,
    subtotal_bs    DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (subtotal_bs >= 0),
    iva_bs         DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (iva_bs >= 0),
    igtf_bs        DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (igtf_bs >= 0),
    total_bs       DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (total_bs >= 0),
    total_ref      DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (total_ref >= 0),
    estado         VARCHAR(20)   NOT NULL DEFAULT 'EMITIDA'
                   CHECK (estado IN ('BORRADOR', 'EMITIDA', 'ANULADA', 'PENDIENTE_CONFIRMACION')),
    fecha_emision  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_facturas_cliente
        FOREIGN KEY (cliente_id) REFERENCES clientes (id),
    CONSTRAINT fk_facturas_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
    CONSTRAINT fk_facturas_tasa
        FOREIGN KEY (tasa_ref_monto) REFERENCES tasas_ref (id),
    CONSTRAINT chk_total_factura CHECK (total_bs = subtotal_bs + iva_bs + igtf_bs)
);

CREATE TABLE detalle_ventas (
    id                  BIGSERIAL PRIMARY KEY,
    factura_id          BIGINT        NOT NULL,
    producto_id         INTEGER       NOT NULL,
    cantidad            DECIMAL(12,3) NOT NULL CHECK (cantidad > 0),
    precio_unitario_bs  DECIMAL(12,2) NOT NULL CHECK (precio_unitario_bs >= 0),
    alicuota_porcentaje DECIMAL(5,2)  NOT NULL CHECK (alicuota_porcentaje IN (0, 8, 16, 31)),
    total_linea_bs      DECIMAL(12,2) NOT NULL CHECK (total_linea_bs >= 0),
    CONSTRAINT fk_detalle_ventas_factura
        FOREIGN KEY (factura_id) REFERENCES facturas (id) ON DELETE CASCADE,
    CONSTRAINT fk_detalle_ventas_producto
        FOREIGN KEY (producto_id) REFERENCES productos (id)
);

CREATE TABLE formas_pago (
    id                  SERIAL PRIMARY KEY,
    codigo              VARCHAR(20) NOT NULL UNIQUE,
    nombre              VARCHAR(40) NOT NULL UNIQUE,
    requiere_referencia BOOLEAN     NOT NULL DEFAULT FALSE
);

CREATE TABLE pagos_venta (
    id            BIGSERIAL PRIMARY KEY,
    factura_id    BIGINT        NOT NULL,
    forma_pago_id INTEGER       NOT NULL,
    monto_origen  DECIMAL(12,2) NOT NULL CHECK (monto_origen >= 0),
    moneda        VARCHAR(3)    NOT NULL DEFAULT 'BS' CHECK (moneda IN ('BS', 'USD')),
    tasa_cambio   DECIMAL(12,4) NOT NULL DEFAULT 1 CHECK (tasa_cambio > 0),
    monto_bs      DECIMAL(12,2) NOT NULL CHECK (monto_bs >= 0),
    referencia    VARCHAR(50),
    CONSTRAINT fk_pagos_venta_factura
        FOREIGN KEY (factura_id) REFERENCES facturas (id) ON DELETE CASCADE,
    CONSTRAINT fk_pagos_venta_forma_pago
        FOREIGN KEY (forma_pago_id) REFERENCES formas_pago (id)
);

CREATE TABLE cuentas_por_cobrar (
    id                  BIGSERIAL PRIMARY KEY,
    factura_id          BIGINT        NOT NULL,
    cliente_id          INTEGER       NOT NULL,
    monto_total_bs      DECIMAL(12,2) NOT NULL CHECK (monto_total_bs > 0),
    saldo_pendiente_bs  DECIMAL(12,2) NOT NULL CHECK (saldo_pendiente_bs >= 0),
    estado              VARCHAR(20)   NOT NULL DEFAULT 'PENDIENTE'
                        CHECK (estado IN ('PENDIENTE', 'SALDADA', 'VENCIDA')),
    fecha_vencimiento   DATE          NOT NULL,
    CONSTRAINT fk_cxc_factura
        FOREIGN KEY (factura_id) REFERENCES facturas (id),
    CONSTRAINT fk_cxc_cliente
        FOREIGN KEY (cliente_id) REFERENCES clientes (id)
);

-- ============================================================
-- 4. MÓDULO DE COMPRAS Y PROVEEDORES
-- ============================================================

CREATE TABLE proveedores (
    id          SERIAL PRIMARY KEY,
    rif         VARCHAR(12)  NOT NULL UNIQUE,
    razon_social VARCHAR(150) NOT NULL,
    direccion   TEXT,
    telefono    VARCHAR(20)
);

CREATE TABLE compras (
    id             BIGSERIAL PRIMARY KEY,
    numero_control VARCHAR(30)   NOT NULL UNIQUE,
    proveedor_id   INTEGER       NOT NULL,
    usuario_id     INTEGER       NOT NULL,
    subtotal_bs    DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (subtotal_bs >= 0),
    iva_bs         DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (iva_bs >= 0),
    total_bs       DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (total_bs >= 0),
    fecha_compra   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_compras_proveedor
        FOREIGN KEY (proveedor_id) REFERENCES proveedores (id),
    CONSTRAINT fk_compras_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
    CONSTRAINT chk_total_compra CHECK (total_bs = subtotal_bs + iva_bs)
);

CREATE TABLE detalle_compras (
    id                BIGSERIAL PRIMARY KEY,
    compra_id         BIGINT        NOT NULL,
    producto_id       INTEGER       NOT NULL,
    cantidad          DECIMAL(12,3) NOT NULL CHECK (cantidad > 0),
    costo_unitario_bs DECIMAL(12,2) NOT NULL CHECK (costo_unitario_bs >= 0),
    CONSTRAINT fk_detalle_compras_compra
        FOREIGN KEY (compra_id) REFERENCES compras (id) ON DELETE CASCADE,
    CONSTRAINT fk_detalle_compras_producto
        FOREIGN KEY (producto_id) REFERENCES productos (id)
);

CREATE TABLE cuentas_por_pagar (
    id                  BIGSERIAL PRIMARY KEY,
    compra_id           BIGINT        NOT NULL,
    proveedor_id        INTEGER       NOT NULL,
    monto_total_bs      DECIMAL(12,2) NOT NULL CHECK (monto_total_bs > 0),
    saldo_pendiente_bs  DECIMAL(12,2) NOT NULL CHECK (saldo_pendiente_bs >= 0),
    fecha_vencimiento   DATE          NOT NULL,
    CONSTRAINT fk_cxp_compra
        FOREIGN KEY (compra_id) REFERENCES compras (id),
    CONSTRAINT fk_cxp_proveedor
        FOREIGN KEY (proveedor_id) REFERENCES proveedores (id)
);

-- ============================================================
-- 5. MÓDULO FISCAL SENIAT Y CIERRES
-- ============================================================

CREATE TABLE cierres_z (
    id             SERIAL PRIMARY KEY,
    usuario_id     INTEGER       NOT NULL,
    fecha          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_ventas_bs DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (total_ventas_bs >= 0),
    total_iva_bs   DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (total_iva_bs >= 0),
    total_igtf_bs  DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (total_igtf_bs >= 0),
    factura_inicio VARCHAR(30)   NOT NULL,
    factura_fin    VARCHAR(30)   NOT NULL,
    CONSTRAINT fk_cierres_z_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
);

CREATE TABLE declaracion_iva (
    id                   SERIAL PRIMARY KEY,
    periodo_mes          INTEGER       NOT NULL CHECK (periodo_mes BETWEEN 1 AND 12),
    periodo_anio         INTEGER       NOT NULL CHECK (periodo_anio >= 2000),
    total_debito_fiscal  DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (total_debito_fiscal >= 0),
    total_credito_fiscal DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (total_credito_fiscal >= 0),
    estatus              VARCHAR(20)   NOT NULL DEFAULT 'BORRADOR'
                         CHECK (estatus IN ('BORRADOR', 'DECLARADA', 'PROCESADA')),
    UNIQUE (periodo_mes, periodo_anio)
);

CREATE TABLE detalle_declaracion_iva (
    id              SERIAL PRIMARY KEY,
    declaracion_id  INTEGER       NOT NULL,
    tipo_transaccion VARCHAR(10)  NOT NULL CHECK (tipo_transaccion IN ('VENTA', 'COMPRA')),
    factura_id      BIGINT,
    compra_id       BIGINT,
    base_imponible  DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (base_imponible >= 0),
    monto_iva       DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (monto_iva >= 0),
    CONSTRAINT fk_detalle_declaracion_declaracion
        FOREIGN KEY (declaracion_id) REFERENCES declaracion_iva (id) ON DELETE CASCADE,
    CONSTRAINT fk_detalle_declaracion_factura
        FOREIGN KEY (factura_id) REFERENCES facturas (id) ON DELETE SET NULL,
    CONSTRAINT fk_detalle_declaracion_compra
        FOREIGN KEY (compra_id) REFERENCES compras (id) ON DELETE SET NULL
);

-- ============================================================
-- ÍNDICES DE RENDIMIENTO
-- ============================================================

CREATE INDEX idx_usuarios_rol ON usuarios (rol_id);
CREATE INDEX idx_productos_categoria ON productos (categoria_id);
CREATE INDEX idx_productos_alicuota ON productos (alicuota_id);
CREATE INDEX idx_kardex_producto_fecha ON kardex_movimientos (producto_id, fecha);
CREATE INDEX idx_facturas_cliente ON facturas (cliente_id);
CREATE INDEX idx_facturas_usuario ON facturas (usuario_id);
CREATE INDEX idx_facturas_fecha ON facturas (fecha_emision);
CREATE INDEX idx_detalle_ventas_factura ON detalle_ventas (factura_id);
CREATE INDEX idx_detalle_ventas_producto ON detalle_ventas (producto_id);
CREATE INDEX idx_pagos_venta_factura ON pagos_venta (factura_id);
CREATE INDEX idx_cxc_cliente ON cuentas_por_cobrar (cliente_id);
CREATE INDEX idx_compras_proveedor ON compras (proveedor_id);
CREATE INDEX idx_detalle_compras_compra ON detalle_compras (compra_id);
CREATE INDEX idx_cxp_proveedor ON cuentas_por_pagar (proveedor_id);
CREATE INDEX idx_cierres_z_usuario ON cierres_z (usuario_id);
CREATE INDEX idx_detalle_declaracion_declaracion ON detalle_declaracion_iva (declaracion_id);
CREATE INDEX idx_bitacora_fecha ON bitacora_auditoria (fecha);
# 📋 CONTEXTO COMPLETO DEL PROYECTO — FERRETERÍA ADRIALGA C.A.

> **Propósito de este documento**: Proporcionar a una IA (o desarrollador) todo el contexto necesario para continuar el desarrollo de este proyecto sin necesidad de explorar el código desde cero. Incluye: estado actual, arquitectura, decisiones tomadas, problemas resueltos, deuda técnica y próximos pasos priorizados.

---

## 1. INFORMACIÓN GENERAL

| Campo | Detalle |
|-------|---------|
| **Proyecto** | Sistema ERP/POS para Ferretería Adrialga C.A. |
| **Stack** | Python 3.12, FastAPI, SQLAlchemy 2.0, Jinja2, SQLite (dev) / PostgreSQL (prod), HTMX, Bootstrap 5 |
| **Base de datos** | `adrialga.db` (SQLite local) / PostgreSQL (producción en Render) |
| **ORM** | SQLAlchemy 2.0 con `Mapped`/`mapped_column` (estilo moderno) |
| **Migraciones** | Alembic |
| **Autenticación** | JWT en cookies HttpOnly + sesiones en BD |
| **Autorización** | RBAC (Role-Based Access Control) con `require_permission` |
| **Frontend** | Server-side rendering con Jinja2 + HTMX para interactividad |
| **Entorno virtual** | `.venv\Scripts\` (Windows) — USO OBLIGATORIO |

---

## 2. CÓMO EJECUTAR EL PROYECTO

### Requisitos previos
- Python 3.12+
- Entorno virtual en `.venv/`

### Comandos de desarrollo (SIEMPRE dentro del .venv)

```bash
# Activar entorno virtual
.venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar migraciones (si aplica)
alembic upgrade head

# Iniciar servidor de desarrollo
uvicorn app.main:app --reload

# Ejecutar tests
pytest
```

### Estructura de la base de datos
- **Archivo**: `adrialga.db` (en la raíz del proyecto)
- **URL de conexión** (en `alembic.ini`): `sqlalchemy.url = sqlite:///./adrialga.db`
- **Configuración de la BD**: `app/db/database.py` (usa `sqlite:///./adrialga.db` por defecto)

---

## 3. ESTRUCTURA DEL PROYECTO

```
├── alembic/                    # Migraciones de base de datos
│   ├── versions/               # Scripts de migración
│   └── env.py                  # Configuración de Alembic
├── app/
│   ├── api/
│   │   └── deps.py             # Dependencias (require_permission, get_current_user)
│   ├── core/
│   │   ├── config.py           # Configuración de la app
│   │   └── security.py         # Hash de contraseñas, JWT
│   ├── db/
│   │   ├── database.py         # Motor, sesión, Base declarativa
│   │   └── init_db.py          # Inicialización de BD
│   ├── models/                 # Modelos SQLAlchemy
│   │   ├── cash.py             # Sesiones de caja, cierres
│   │   ├── fiscal.py           # Cierres Z, retenciones, declaraciones
│   │   ├── inventory.py        # Categorías, marcas, productos, kardex
│   │   ├── purchases.py        # Proveedores, compras, CxP
│   │   ├── sales.py            # Clientes, facturas, pagos, CxC
│   │   └── security.py         # Usuarios, roles, permisos, auditoría
│   ├── routers/                # Controladores FastAPI
│   │   ├── auth.py             # Login, logout, usuarios, roles, permisos
│   │   ├── dashboard.py        # KPIs, gráficos, auditoría, reportes
│   │   ├── fiscal.py           # Cierre Z, libros, retenciones, caja
│   │   ├── inventory.py        # Productos, categorías, marcas, kardex
│   │   ├── purchases.py        # Proveedores, compras, CxP
│   │   ├── sales.py            # POS, clientes, ventas
│   │   └── seniat.py           # Consulta RIF SENIAT
│   ├── schemas/                # Esquemas Pydantic
│   ├── services/               # Lógica de negocio
│   │   ├── bcv_scraper.py      # Scraper tasa BCV
│   │   ├── fiscal_service.py   # Lógica fiscal (caja, reporte X/Z)
│   │   └── seniat_service.py   # Cliente SENIAT
│   ├── static/                 # CSS, JS
│   ├── templates/              # Plantillas Jinja2
│   │   ├── auth/               # Login
│   │   ├── dashboard/          # Dashboard, bitácora
│   │   ├── fiscal/             # Cierre Z, libros
│   │   ├── inventory/          # Inventario, entradas, kardex
│   │   ├── purchases/          # Compras, proveedores, CxP
│   │   ├── sales/              # POS, devoluciones
│   │   ├── security/           # Usuarios
│   │   ├── base.html           # Plantilla base
│   │   └── partial.html        # Plantilla para peticiones HTMX
│   └── main.py                 # Punto de entrada FastAPI
├── scripts/                    # Scripts de utilidad
├── tests/                      # Tests
├── alembic.ini                 # Configuración de Alembic
├── requirements.txt            # Dependencias
└── adrialga.db                 # Base de datos SQLite (NO BORRAR)
```

---

## 4. ESTADO ACTUAL DEL PROYECTO

### 4.1. Último cambio realizado (COMPLETADO ✅)

**Problema**: La ruta `GET /compras/proveedores` devolvía error 500 porque la columna `activo` no existía en la tabla `proveedores` de la base de datos.

**Solución aplicada**:
1. Se corrigió `alembic/env.py`:
   - **Antes**: `from app.database import Base` (no existía)
   - **Después**: `from app.db.database import Base` (ruta correcta)
2. Se creó la migración `4e13f273a615_agregar_columna_activo_a_tabla_.py` que agrega la columna `activo` (BOOLEAN, NOT NULL, DEFAULT '1') a la tabla `proveedores`.
3. Se eliminó la migración duplicada `4e13f202a615` que contenía cambios no deseados (tabla `marcas`, `clientes.limite_credito`, `facturas.sesion_caja_id`).
4. Se aplicó la migración exitosamente.

**Verificación**: La tabla `proveedores` ahora tiene la columna `activo` (BOOLEAN, NOT NULL, DEFAULT '1').

### 4.2. Migraciones de base de datos

**IMPORTANTE**: La base de datos `adrialga.db` fue creada originalmente con `Base.metadata.create_all()` y NO tiene un historial de migraciones previo. La migración `4e13f273a615` es la PRIMERA y ÚNICA migración en el historial de Alembic.

**Consecuencia**: Si se ejecuta `alembic revision --autogenerate`, Alembic detectará TODAS las tablas existentes en los modelos como "nuevas" (porque no hay migraciones base). **NO se debe hacer `alembic revision --autogenerate` sin antes crear una migración base** que refleje el estado actual de la BD.

**Solución recomendada** (para futuras migraciones):
1. Crear una migración base que refleje el estado actual de la BD (o usar `alembic stamp` para marcar el estado actual).
2. Luego sí, las migraciones subsiguientes con `--autogenerate` solo detectarán cambios incrementales.

---

## 5. ARQUITECTURA DETALLADA

### 5.1. Modelos de datos (tablas)

#### Módulo de Compras (`app/models/purchases.py`)
| Tabla | Descripción | Campos clave |
|-------|-------------|--------------|
| `proveedores` | Proveedores | id, rif (único), razon_social, direccion, telefono, contacto, **activo** |
| `compras` | Compras a proveedores | id, numero_control (único), proveedor_id, usuario_id, subtotal_bs, iva_bs, total_bs, fecha_compra |
| `detalle_compras` | Detalle de compras | id, compra_id, producto_id, cantidad, costo_unitario_bs |
| `cuentas_por_pagar` | Cuentas por pagar | id, compra_id, proveedor_id, monto_total_bs, saldo_pendiente_bs, fecha_vencimiento |

#### Módulo de Inventario (`app/models/inventory.py`)
| Tabla | Descripción | Campos clave |
|-------|-------------|--------------|
| `categorias` | Categorías de productos | id, nombre (único), descripcion |
| `marcas` | Marcas de productos | id, nombre (único), descripcion, activo |
| `configuracion_fiscal` | Alícuotas de IVA | id, codigo (G/R/A/E), porcentaje (0/8/16/31), descripcion |
| `productos` | Productos | id, codigo_barras (único), descripcion, categoria_id, marca_id, alicuota_id, precio_ref, stock_actual, stock_minimo, activo |
| `kardex_movimientos` | Movimientos de inventario | id, producto_id, tipo_movimiento (ENTRADA/SALIDA/AJUSTE), cantidad, costo_ref, origen_id, fecha |

#### Módulo de Ventas (`app/models/sales.py`)
| Tabla | Descripción | Campos clave |
|-------|-------------|--------------|
| `clientes` | Clientes | id, cedula_rif (único), razon_social, direccion, telefono, email, limite_credito |
| `tasas_ref` | Tasa de cambio | id, fecha, monto_bs, origen (BCV/MANUAL) |
| `correlativos_fiscales` | Correlativos de factura | id, tipo_documento, serie, ultimo_numero |
| `facturas` | Facturas | id, numero_factura (único), correlativo, cliente_id, usuario_id, tasa_ref_id, sesion_caja_id, subtotal_bs, iva_bs, igtf_bs, total_bs, total_ref, estado, fecha_emision |
| `detalle_ventas` | Detalle de facturas | id, factura_id, producto_id, cantidad, precio_unitario_bs, alicuota_porcentaje, total_linea_bs |
| `formas_pago` | Formas de pago | id, codigo, nombre, requiere_referencia |
| `pagos_venta` | Pagos de facturas | id, factura_id, forma_pago_id, monto_origen, moneda (BS/USD), tasa_cambio, monto_bs, referencia |
| `cuentas_por_cobrar` | Cuentas por cobrar | id, factura_id, cliente_id, monto_total_bs, saldo_pendiente_bs, estado, fecha_vencimiento |

#### Módulo Fiscal (`app/models/fiscal.py`)
| Tabla | Descripción |
|-------|-------------|
| `cierres_z` | Cierres Z |
| `retenciones_iva` | Retenciones de IVA |
| `retenciones_islr` | Retenciones de ISLR |
| `declaraciones_iva` | Declaraciones de IVA |
| `detalle_declaraciones_iva` | Detalle de declaraciones |

#### Módulo de Caja (`app/models/cash.py`)
| Tabla | Descripción |
|-------|-------------|
| `sesiones_caja` | Sesiones de caja (apertura/cierre) |
| `cierres_caja` | Cierres de caja (Reporte Z) |

#### Módulo de Seguridad (`app/models/security.py`)
| Tabla | Descripción |
|-------|-------------|
| `usuarios` | Usuarios del sistema |
| `roles` | Roles (Superusuario, Administrador, Cajero, etc.) |
| `modulos` | Módulos del sistema |
| `permisos` | Permisos (ver, crear, editar, eliminar) |
| `roles_permisos` | Relación rol-permiso |
| `sesiones_usuarios` | Sesiones activas |
| `bitacora_auditoria` | Bitácora de auditoría |

### 5.2. Rutas principales (endpoints)

#### Autenticación (`/app/routers/auth.py`)
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/login` | Página de login |
| POST | `/login` | Procesar login |
| GET | `/logout` | Cerrar sesión |
| GET | `/usuarios` | Vista de usuarios |
| POST | `/usuarios` | Crear usuario |
| PUT | `/usuarios/{id}` | Actualizar usuario |
| GET | `/roles` | Listar roles |
| GET | `/roles/{id}/permisos` | Obtener permisos de rol |
| POST | `/roles/{id}/permisos` | Asignar permisos a rol |

#### Dashboard (`/app/routers/dashboard.py`)
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Dashboard principal |
| GET | `/grafico-ventas` | Datos para gráfico |
| GET | `/auditoria` | Bitácora de auditoría |
| GET | `/auditoria/data` | Datos de auditoría |
| GET | `/reportes/mas-vendidos` | Top productos |
| GET | `/reportes/rentabilidad` | Rentabilidad |
| GET | `/reportes/ventas-periodo` | Ventas por período |

#### Inventario (`/app/routers/inventory.py`)
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/inventario/` | Vista principal |
| GET | `/inventario/entradas` | Entradas de inventario |
| GET | `/inventario/kardex` | Consulta de kardex |
| GET | `/inventario/tabla` | Tabla de productos (HTMX) |
| POST | `/inventario/productos` | Crear producto |
| PUT | `/inventario/productos/{id}` | Actualizar producto |
| DELETE | `/inventario/productos/{id}` | Desactivar producto |
| POST | `/inventario/entradas` | Registrar entrada |
| GET | `/inventario/kardex/data` | Datos de kardex |
| GET | `/inventario/productos/data` | Productos JSON |
| GET/POST/PUT/DELETE | `/inventario/categorias` | CRUD categorías |
| GET/POST/PUT/DELETE | `/inventario/marcas` | CRUD marcas |
| GET | `/inventario/alicuotas` | Listar alícuotas |

#### Compras (`/app/routers/purchases.py`)
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/compras/proveedores` | Vista de proveedores |
| GET | `/compras/proveedores/data` | Proveedores JSON |
| POST | `/compras/proveedores` | Crear proveedor |
| PUT | `/compras/proveedores/{id}` | Actualizar proveedor |
| DELETE | `/compras/proveedores/{id}` | Desactivar proveedor |
| GET | `/compras` | Vista de compras |
| POST | `/compras/nueva` | Registrar compra |
| GET | `/compras/cxp` | Cuentas por pagar |
| GET | `/compras/cxp/data` | Datos CxP |
| POST | `/compras/cxp/{id}/abonar` | Abonar a CxP |

#### Ventas (`/app/routers/sales.py`)
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/pos` | Vista POS |
| GET | `/pos/devoluciones` | Devoluciones |
| GET | `/configuracion` | Configuración de tasa |
| POST | `/pos/tasa-ref` | Actualizar tasa |
| GET | `/pos/buscar-producto` | Buscar producto |
| GET | `/pos/buscar-cliente` | Buscar cliente |
| PUT | `/pos/clientes/{id}` | Actualizar cliente |
| GET | `/api/clientes/buscar` | Buscar cliente por cédula |
| POST | `/api/clientes/rapido` | Registrar cliente rápido |
| POST | `/pos/procesar-venta` | Procesar venta |

#### Fiscal (`/app/routers/fiscal.py`)
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/fiscal/cierre-z` | Vista Cierre Z |
| GET | `/fiscal/libro-ventas` | Libro de ventas |
| GET | `/fiscal/libro-compras` | Libro de compras |
| POST | `/fiscal/caja/abrir` | Abrir caja |
| GET | `/fiscal/caja/reporte-x` | Reporte X |
| POST | `/fiscal/caja/cerrar` | Cerrar caja |
| POST | `/fiscal/cierre-z/generar` | Generar Cierre Z |
| GET | `/fiscal/libro-ventas/data` | Datos libro ventas |
| GET | `/fiscal/libro-compras/data` | Datos libro compras |
| POST | `/compras/{id}/generar-retencion-iva` | Generar retención IVA |
| POST | `/compras/{id}/generar-retencion-islr` | Generar retención ISLR |
| GET | `/compras/retencion/{id}` | Ver comprobante |

---

## 6. DECISIONES TÉCNICAS IMPORTANTES

### 6.1. Patrón de autenticación
- **JWT en cookies HttpOnly** (no en localStorage) para seguridad contra XSS.
- **Sesiones en BD** (`sesiones_usuarios`) para poder revocar tokens.
- **RBAC** con `require_permission(modulo, accion)` en cada ruta.

### 6.2. Patrón HTMX
- Las vistas devuelven HTML parcial o completo según la cabecera `HX-Request`.
- Si es HTMX, se usa `partial.html` como base; si no, `base.html`.
- Esto evita recargar el sidebar en cada navegación.

### 6.3. Manejo de transacciones
- Las operaciones de escritura (ventas, compras) usan transacciones atómicas con `try/except` y `db.rollback()`.
- Se usa `db.flush()` para obtener IDs sin hacer commit.

### 6.4. Moneda
- Los montos se almacenan en Bs (Bolívares) con `Numeric(12, 2)`.
- La tasa de cambio se guarda en `tasas_ref` con `Numeric(12, 4)`.
- Los totales en USD se calculan dividiendo entre la tasa.

### 6.5. Soft delete
- Los registros se desactivan con `activo = False` en lugar de eliminarse físicamente.
- Aplica a: proveedores, productos, marcas, usuarios.

---

## 7. PROBLEMAS CONOCIDOS Y DEUDA TÉCNICA

### 7.1. Problemas críticos
1. **Sin migración base en Alembic**: La BD se creó con `create_all()`. La primera migración `4e13f273a615` solo agrega la columna `activo`. Si se ejecuta `--autogenerate`, detectará todas las tablas como nuevas. **Se necesita crear una migración base o usar `alembic stamp`**.

2. **Lógica de negocio en routers**: Los archivos `purchases.py` (425 líneas), `inventory.py` (794 líneas), `sales.py` (580 líneas) y `fiscal.py` (673 líneas) concentran demasiada lógica. Deberían delegar en `services/`.

3. **Manejo inconsistente de errores**: Mezcla de `JSONResponse` con `raise HTTPException`. Algunos endpoints no capturan excepciones.

### 7.2. Deuda técnica media
4. **Código duplicado**: La detección HTMX (`is_htmx`/`base_template`) se repite en ~20 vistas. Debería ser un middleware o dependencia.
5. **`templates = Jinja2Templates(...)`** se instancia en cada router; debería ser un singleton.
6. **Schemas Pydantic subutilizados**: En `inventory.py` y `auth.py` se usa `request.form()` en vez de los schemas definidos.
7. **Sin tests de integración** para la mayoría de los flujos.

### 7.3. Bugs potenciales detectados
8. En `purchases.py` línea 414: `cxp.estado = "PAGADA"` asume que existe el estado "PAGADA" pero el modelo `CuentaPorPagar` no tiene campo `estado` (solo `saldo_pendiente_bs`). **REVISAR**.
9. En `fiscal.py` línea 239: `cierre.total_ventas_bs` se usa antes de ser asignado (debería ser `cierre_data` o similar). **REVISAR**.
10. En `dashboard.py` línea 66: `require_roles(["Superusuario", "Administrador"])` restringe el dashboard solo a estos roles; los cajeros no podrían verlo. **VERIFICAR si es intencional**.

---

## 8. MATRIZ DE ESTADO CRUD POR MÓDULO

| Módulo | Entidad | Create | Read | Update | Delete/Disable |
|--------|---------|--------|------|--------|----------------|
| **Compras** | Proveedores | ✅ | ✅ | ✅ | ⚠️ Soft |
| | Compras | ✅ | ⚠️ Listado | ❌ | ❌ |
| | Cuentas por Pagar | ⚠️ Auto | ✅ | ⚠️ Abonos | ❌ |
| **Inventario** | Productos | ✅ | ✅ | ✅ | ⚠️ Soft |
| | Categorías | ✅ | ✅ | ✅ | ✅ Protegido |
| | Marcas | ✅ | ✅ | ✅ | ⚠️ Soft |
| | Kardex | ⚠️ Auto | ✅ | ❌ | ❌ |
| | Entradas/Ajustes | ✅ | ❌ | ❌ | ❌ |
| **Ventas** | Clientes | ⚠️ Rápido | ✅ | ✅ | ❌ |
| | Ventas (POS) | ✅ | ⚠️ Parcial | ❌ | ❌ |
| | Devoluciones | ❌ | ❌ | ❌ | ❌ |
| | Cuentas por Cobrar | ⚠️ Auto | ⚠️ Parcial | ❌ | ❌ |
| **Fiscal** | Cierre Z | ✅ | ✅ | ❌ | ❌ |
| | Libro Ventas | ⚠️ Auto | ✅ | ❌ | ❌ |
| | Libro Compras | ⚠️ Auto | ✅ | ❌ | ❌ |
| | Retenciones | ✅ | ⚠️ Parcial | ❌ | ❌ |
| | Caja | ✅ | ✅ | ❌ | ❌ |
| **Seguridad** | Usuarios | ✅ | ✅ | ✅ | ⚠️ Soft |
| | Roles | ⚠️ Listar | ⚠️ Parcial | ⚠️ Permisos | ❌ |
| **Dashboard** | KPIs | — | ✅ | — | — |
| | Auditoría | ⚠️ Auto | ✅ | ❌ | ❌ |
| | Reportes | — | ✅ | — | — |
| **SENIAT** | Consulta RIF | — | ✅ | — | — |

**Leyenda**: ✅ Completo | ⚠️ Parcial/Incompleto | ❌ No existe | Auto = Automático

---

## 9. PRÓXIMOS PASOS RECOMENDADOS (PRIORIZADOS)

### Prioridad Alta (crítico para operación)
1. **Crear migración base de Alembic** para que las migraciones futuras funcionen correctamente.
2. **CRUD de Clientes completo** (hoy solo hay alta rápida desde POS y edición; falta listado con búsqueda, paginación y desactivación).
3. **CRUD de Compras** (solo existe creación y listado; falta ver detalle, anular, y editar).
4. **Módulo de Devoluciones** (la ruta `/pos/devoluciones` existe pero no tiene lógica de negocio).
5. **Anulación de facturas** (hoy no se puede anular una venta, solo se crean).

### Prioridad Media
6. **CRUD de Cuentas por Cobrar** (falta gestión de cobros, abonos, reporte de vencidas).
7. **CRUD de Cuentas por Pagar** (falta gestión de pagos, abonos, reporte de vencidas).
8. **Gestión de Roles** (solo se pueden listar y asignar permisos; falta crear/editar/eliminar roles).
9. **Reportes gerenciales** (existen endpoints pero falta la interfaz en `reports/index.html`).

### Prioridad Baja (mejora continua)
10. **Refactorizar routers** para mover lógica de negocio a `services/`.
11. **Crear middleware HTMX** para eliminar duplicación de `is_htmx`/`base_template`.
12. **Unificar manejo de errores** con un manejador global de excepciones.
13. **Aumentar cobertura de tests** (actualmente solo hay tests de servicios y algunos de integración).

---

## 10. CÓMO CONTINUAR (GUÍA PARA LA IA)

Si estás leyendo esto, eres una IA que continuará el desarrollo de este proyecto. Sigue estas pautas:

### Reglas obligatorias
1. **SIEMPRE** usa el entorno virtual `.venv\Scripts\` para ejecutar comandos de Python.
2. **NUNCA** borres la base de datos `adrialga.db` ni uses `Base.metadata.create_all()` para aplicar cambios en modelos existentes.
3. **SIEMPRE** usa Alembic para cambios de esquema: `alembic revision --autogenerate -m "descripción"` y luego `alembic upgrade head`.
4. **NUNCA** ejecutes `alembic revision --autogenerate` sin antes resolver el problema de la migración base (ver sección 4.2).

### Flujo de trabajo recomendado
1. Lee este documento completo.
2. Explora los archivos relevantes en `app/models/`, `app/routers/`, `app/schemas/`, `app/services/`.
3. Revisa las plantillas en `app/templates/` para entender el patrón HTMX.
4. Ejecuta la app con `uvicorn app.main:app --reload` para probar.
5. Ejecuta los tests con `pytest` para verificar que no rompiste nada.

### Archivos clave para entender el patrón
- `app/main.py` — Punto de entrada, registro de routers.
- `app/api/deps.py` — Dependencias de autenticación y permisos.
- `app/db/database.py` — Configuración de BD.
- `app/routers/purchases.py` — Ejemplo de CRUD completo (proveedores).
- `app/routers/inventory.py` — Ejemplo de CRUD con HTMX (categorías, marcas).
- `app/templates/base.html` — Plantilla base con sidebar.
- `app/templates/partial.html` — Plantilla para peticiones HTMX.

---

*Documento generado el 2026-08-14. Última actualización: 2026-08-14.*
"""
Router de Inventario — Gestión de Productos, Categorías y Kardex.

Rutas:
- GET  /inventario/            : Vista principal del inventario.
- GET  /inventario/tabla       : Parcial HTMX con tabla paginada/filtrada.
- POST /inventario/productos   : Crea producto y genera movimiento Kardex.
- PUT  /inventario/productos/{id} : Actualiza producto.
- GET  /inventario/categorias  : Lista categorías (JSON).
- POST /inventario/categorias  : Crea categoría (JSON/HTMX).
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.database import get_db
from app.models.inventory import Categoria, ConfiguracionFiscal, KardexMovimiento, Producto
from app.schemas.inventory import (
    CategoriaCreate,
    CategoriaResponse,
    CategoriaUpdate,
    ProductoCreate,
    ProductoResponse,
    ProductoUpdate,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ============================================================
# Modelos auxiliares
# ============================================================

class CategoriaRapida(BaseModel):
    """Schema mínimo para selects de categorías."""
    id: int
    nombre: str

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# VISTAS
# ============================================================

@router.get("/inventario/", response_class=HTMLResponse)
async def inventario_index(
    request: Request,
    usuario=Depends(require_permission("inventario", "lectura")),
):
    """Vista principal del módulo de inventario."""
    # Detectar petición HTMX para evitar duplicar el sidebar
    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="inventory/index.html",
        context={
            "usuario": usuario,
            "base_template": base_template,
            "productos": [],
            "total_pages": 1,
            "page": 1,
            "total": 0,
            "q": "",
            "categoria_id": 0,
        },
    )


# ============================================================
# TABLA PRODUCTOS (HTMX)
# ============================================================

@router.get("/inventario/entradas", response_class=HTMLResponse)
async def entradas_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("inventario", "lectura")),
):
    """Vista de Entradas / Ajustes de Inventario."""
    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="inventory/entradas.html",
        context={"usuario": usuario, "base_template": base_template},
    )


@router.get("/inventario/kardex", response_class=HTMLResponse)
async def kardex_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("inventario", "lectura")),
):
    """Vista de consulta del Kardex / Movimientos de Inventario."""
    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="inventory/kardex.html",
        context={"usuario": usuario, "base_template": base_template},
    )


@router.get("/inventario/tabla", response_class=HTMLResponse)
async def tabla_productos(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("inventario", "lectura")),
    q: str = Query(default="", description="Búsqueda por texto"),
    categoria_id: int = Query(default=0, description="Filtro por categoría"),
    page: int = Query(default=1, ge=1, description="Número de página"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items por página"),
):
    """
    Devuelve el parcial HTMX con la tabla de productos paginada y filtrada.

    Parámetros:
    - q: búsqueda en código_barras o descripción.
    - categoria_id: 0 = todas.
    - page / per_page: paginación.
    """
    stmt = (
        select(Producto, Categoria, ConfiguracionFiscal)
        .join(Categoria, Producto.categoria_id == Categoria.id)
        .join(ConfiguracionFiscal, Producto.alicuota_id == ConfiguracionFiscal.id)
        .where(Producto.activo.is_(True))
    )

    # Filtro de texto
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Producto.codigo_barras.ilike(like),
                Producto.descripcion.ilike(like),
            )
        )

    # Filtro de categoría
    if categoria_id and categoria_id > 0:
        stmt = stmt.where(Producto.categoria_id == categoria_id)

    # Ordenar por código de barras
    stmt = stmt.order_by(Producto.codigo_barras)

    # Paginación
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.execute(
        stmt.offset((page - 1) * per_page).limit(per_page)
    ).unique().all()

    # Construir respuesta
    rows = []
    for prod, cat, alic in items:
        rows.append(
            {
                "id": prod.id,
                "codigo_barras": prod.codigo_barras,
                "descripcion": prod.descripcion,
                "categoria_nombre": cat.nombre,
                "precio_ref": prod.precio_ref,
                "stock_actual": prod.stock_actual,
                "stock_minimo": prod.stock_minimo,
                "alicuota_codigo": alic.codigo,
                "alicuota_porcentaje": alic.porcentaje,
                "activo": prod.activo,
            }
        )

    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1

    return templates.TemplateResponse(
        request=request,
        name="inventory/_partials/tabla_productos.html",
        context={
            "productos": rows,
            "q": q,
            "categoria_id": categoria_id,
            "page": page,
            "per_page": per_page,
            "total": total or 0,
            "total_pages": total_pages,
            "usuario": usuario,
        },
    )


# ============================================================
# CRUD PRODUCTOS
# ============================================================

@router.post("/inventario/productos", response_class=JSONResponse)
async def crear_producto(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("inventario", "escritura")),
):
    """
    Crea un producto.

    Si stock_actual > 0 genera automáticamente un movimiento Kardex
    tipo 'ENTRADA' (Saldo Inicial) dentro de la misma transacción.
    """
    form = await request.form()

    # Leer campos del formulario
    codigo_barras = (form.get("codigo_barras") or "").strip()
    descripcion = (form.get("descripcion") or "").strip()
    categoria_id = int(form.get("categoria_id") or 0)
    alicuota_id = int(form.get("alicuota_id") or 0)
    precio_ref = Decimal(form.get("precio_ref") or "0.00")
    stock_actual = Decimal(form.get("stock_actual") or "0.000")
    stock_minimo = Decimal(form.get("stock_minimo") or "0.000")
    activo = bool(form.get("activo"))

    # Validar existencia de categoría y alícuota
    if not db.get(Categoria, categoria_id):
        return JSONResponse(
            status_code=400,
            content={"error": "Categoría inválida."},
        )
    if not db.get(ConfiguracionFiscal, alicuota_id):
        return JSONResponse(
            status_code=400,
            content={"error": "Alícuota fiscal inválida."},
        )

    # Crear producto
    producto = Producto(
        codigo_barras=codigo_barras,
        descripcion=descripcion,
        categoria_id=categoria_id,
        alicuota_id=alicuota_id,
        precio_ref=precio_ref,
        stock_actual=stock_actual,
        stock_minimo=stock_minimo,
        activo=activo,
    )
    db.add(producto)
    db.flush()  # Para obtener producto.id

    # Generar movimiento Kardex si hay stock inicial
    if stock_actual > 0:
        kardex = KardexMovimiento(
            producto_id=producto.id,
            tipo_movimiento="ENTRADA",
            cantidad=stock_actual,
            costo_ref=precio_ref,
            origen_id=None,
            fecha=datetime.now(timezone.utc),
        )
        db.add(kardex)

    db.commit()

    # HTMX redirect a la tabla
    hx_request = request.headers.get("HX-Request", "").lower() == "true"
    if hx_request:
        return JSONResponse(
            status_code=200,
            headers={"HX-Redirect": "/inventario/"},
            content={"ok": True},
        )
    return JSONResponse(status_code=201, content={"ok": True})


@router.put("/inventario/productos/{producto_id}", response_class=JSONResponse)
async def actualizar_producto(
    request: Request,
    producto_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("inventario", "escritura")),
):
    """
    Actualiza datos de un producto.

    Nota: No se permite modificar stock_actual directamente por este endpoint
    (debe hacerse por Kardex/Compras).
    """
    producto = db.get(Producto, producto_id)
    if not producto:
        return JSONResponse(status_code=404, content={"error": "Producto no encontrado"})

    form = await request.form()

    # Campos permitidos
    if "codigo_barras" in form:
        producto.codigo_barras = (form.get("codigo_barras") or "").strip()
    if "descripcion" in form:
        producto.descripcion = (form.get("descripcion") or "").strip()
    if "categoria_id" in form:
        cat_id = int(form.get("categoria_id") or 0)
        if db.get(Categoria, cat_id):
            producto.categoria_id = cat_id
    if "precio_ref" in form:
        producto.precio_ref = Decimal(form.get("precio_ref") or "0.00")
    if "stock_minimo" in form:
        producto.stock_minimo = Decimal(form.get("stock_minimo") or "0.000")
    if "activo" in form:
        producto.activo = bool(form.get("activo"))

    db.commit()

    hx_request = request.headers.get("HX-Request", "").lower() == "true"
    if hx_request:
        return JSONResponse(
            status_code=200,
            headers={"HX-Redirect": "/inventario/"},
            content={"ok": True},
        )
    return JSONResponse(status_code=200, content={"ok": True})


# ============================================================
# ENTRADAS / AJUSTES DE INVENTARIO
# ============================================================

@router.post("/inventario/entradas", response_class=JSONResponse)
async def registrar_entrada(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("inventario", "escritura")),
):
    """
    Registra una entrada o ajuste positivo de inventario.

    Actualiza `stock_actual` del producto y genera un movimiento
    Kardex tipo 'ENTRADA' o 'AJUSTE' dentro de la misma transacción.
    """
    form = await request.form()

    producto_id = int(form.get("producto_id") or 0)
    cantidad = Decimal(form.get("cantidad") or "0")
    costo_ref = Decimal(form.get("costo_ref") or "0.00")
    motivo = (form.get("motivo") or "").strip()
    tipo = (form.get("tipo_movimiento") or "ENTRADA").strip().upper()

    # Validar tipo de movimiento permitido
    if tipo not in ("ENTRADA", "AJUSTE"):
        return JSONResponse(
            status_code=400,
            content={"error": "Tipo de movimiento inválido. Use ENTRADA o AJUSTE."},
        )

    # Validar cantidad positiva
    if cantidad <= 0:
        return JSONResponse(
            status_code=400,
            content={"error": "La cantidad debe ser mayor a cero."},
        )

    # Validar producto
    producto = db.get(Producto, producto_id)
    if not producto or not producto.activo:
        return JSONResponse(
            status_code=400,
            content={"error": "Producto no válido o inactivo."},
        )

    # Actualizar stock y crear movimiento Kardex (transacción atómica)
    producto.stock_actual += cantidad

    kardex = KardexMovimiento(
        producto_id=producto.id,
        tipo_movimiento=tipo,
        cantidad=cantidad,
        costo_ref=costo_ref,
        origen_id=None,
        fecha=datetime.now(timezone.utc),
    )
    db.add(kardex)
    db.commit()
    db.refresh(producto)

    return JSONResponse(
        status_code=201,
        content={
            "ok": True,
            "producto_id": producto.id,
            "nuevo_stock": float(producto.stock_actual),
            "kardex_id": kardex.id,
            "tipo_movimiento": tipo,
            "motivo": motivo,
        },
    )


# ============================================================
# KARDEX / MOVIMIENTOS (JSON)
# ============================================================

@router.get("/inventario/kardex/data", response_class=JSONResponse)
async def kardex_data(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("inventario", "lectura")),
    producto_id: Optional[int] = Query(default=None, description="Filtro por producto"),
    tipo_movimiento: Optional[str] = Query(default=None, description="ENTRADA, SALIDA, AJUSTE"),
    fecha_desde: Optional[date] = Query(default=None, description="Fecha inicial"),
    fecha_hasta: Optional[date] = Query(default=None, description="Fecha final"),
    page: int = Query(default=1, ge=1, description="Número de página"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items por página"),
):
    """
    Consulta paginada del Kardex con filtros por producto, fechas y tipo.

    Calcula stock inicial y final acumulado para cada movimiento.
    """
    filtros = []

    if producto_id:
        filtros.append(KardexMovimiento.producto_id == producto_id)
    if tipo_movimiento:
        filtros.append(KardexMovimiento.tipo_movimiento == tipo_movimiento.upper())
    if fecha_desde:
        filtros.append(KardexMovimiento.fecha >= fecha_desde)
    if fecha_hasta:
        filtros.append(KardexMovimiento.fecha <= fecha_hasta)

    stmt = (
        select(KardexMovimiento, Producto)
        .join(Producto, KardexMovimiento.producto_id == Producto.id)
        .where(and_(*filtros))
        .order_by(KardexMovimiento.fecha.desc(), KardexMovimiento.id.desc())
    )

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.execute(
        stmt.offset((page - 1) * per_page).limit(per_page)
    ).all()

    # Calcular stock acumulado para cada movimiento
    movimientos = []
    for kardex, producto in items:
        # Stock inicial = suma de movimientos anteriores al actual
        stock_inicial = db.scalar(
            select(func.coalesce(func.sum(KardexMovimiento.cantidad), 0)).where(
                KardexMovimiento.producto_id == kardex.producto_id,
                or_(
                    KardexMovimiento.fecha < kardex.fecha,
                    and_(
                        KardexMovimiento.fecha == kardex.fecha,
                        KardexMovimiento.id < kardex.id,
                    ),
                ),
            )
        ) or Decimal("0")

        # Stock final según tipo de movimiento
        if kardex.tipo_movimiento == "SALIDA":
            stock_final = stock_inicial - kardex.cantidad
        else:
            stock_final = stock_inicial + kardex.cantidad

        movimientos.append(
            {
                "id": kardex.id,
                "fecha": kardex.fecha.isoformat(),
                "producto_id": producto.id,
                "codigo_barras": producto.codigo_barras,
                "descripcion": producto.descripcion,
                "tipo_movimiento": kardex.tipo_movimiento,
                "cantidad": float(kardex.cantidad),
                "costo_ref": float(kardex.costo_ref),
                "stock_inicial": float(stock_inicial),
                "stock_final": float(stock_final),
                "referencia": kardex.origen_id,
            }
        )

    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1

    return {
        "movimientos": movimientos,
        "total": total or 0,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


# ============================================================
# CATEGORÍAS (JSON + HTMX rápido)
# ============================================================

@router.get("/inventario/productos/data", response_class=JSONResponse)
async def productos_data(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("inventario", "lectura")),
):
    """Devuelve lista de productos activos en JSON para selects/dropdowns."""
    productos = db.execute(
        select(Producto)
        .where(Producto.activo.is_(True))
        .order_by(Producto.codigo_barras)
    ).scalars().all()
    return {
        "productos": [
            {
                "id": p.id,
                "codigo_barras": p.codigo_barras,
                "descripcion": p.descripcion,
                "precio_ref": float(p.precio_ref),
                "stock_actual": float(p.stock_actual),
            }
            for p in productos
        ]
    }


@router.get("/inventario/categorias", response_class=JSONResponse)
async def listar_categorias(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("inventario", "lectura")),
    q: str = Query(default="", description="Búsqueda por nombre"),
):
    """Devuelve lista de categorías para selects."""
    stmt = select(Categoria).order_by(Categoria.nombre)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(Categoria.nombre.ilike(like))

    categorias = db.execute(stmt).scalars().all()
    return {"categorias": [{"id": c.id, "nombre": c.nombre} for c in categorias]}


@router.post("/inventario/categorias", response_class=JSONResponse)
async def crear_categoria(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("inventario", "escritura")),
):
    """Crea una categoría desde modal HTMX o JSON."""
    form = await request.form()
    nombre = (form.get("nombre") or "").strip()
    descripcion = (form.get("descripcion") or "").strip()

    if not nombre:
        return JSONResponse(
            status_code=400,
            content={"error": "El nombre es obligatorio."},
        )

    existente = db.scalar(select(Categoria).where(Categoria.nombre == nombre))
    if existente:
        return JSONResponse(
            status_code=409,
            content={"error": "Ya existe una categoría con ese nombre."},
        )

    categoria = Categoria(nombre=nombre, descripcion=descripcion)
    db.add(categoria)
    db.commit()
    db.refresh(categoria)

    return JSONResponse(status_code=201, content={"id": categoria.id, "nombre": categoria.nombre})


@router.get("/inventario/alicuotas", response_class=JSONResponse)
async def listar_alicuotas(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("inventario", "lectura")),
):
    """Devuelve lista de alícuotas fiscales para selects."""
    alicuotas = db.scalars(select(ConfiguracionFiscal).order_by(ConfiguracionFiscal.codigo)).all()
    return {
        "alicuotas": [
            {"id": a.id, "codigo": a.codigo, "porcentaje": float(a.porcentaje)}
            for a in alicuotas
        ]
    }

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

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func, or_, select
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

    class Config:
        from_attributes = True


# ============================================================
# VISTAS
# ============================================================

@router.get("/inventario/", response_class=HTMLResponse)
async def inventario_index(
    request: Request,
    usuario=Depends(require_permission("inventario", "lectura")),
):
    """Vista principal del módulo de inventario."""
    return templates.TemplateResponse(
        request=request,
        name="inventory/index.html",
        context={"usuario": usuario},
    )


# ============================================================
# TABLA PRODUCTOS (HTMX)
# ============================================================

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
# CATEGORÍAS (JSON + HTMX rápido)
# ============================================================

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

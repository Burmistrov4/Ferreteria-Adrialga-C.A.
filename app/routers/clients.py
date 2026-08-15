"""
Router de Clientes — Gestión integral de clientes.

Rutas:
- GET  /clientes                    : Vista principal con listado paginado y búsqueda.
- GET  /clientes/tabla              : Parcial HTMX con tabla de clientes.
- POST /clientes                    : Crear cliente (validación de Cédula/RIF único).
- PUT  /clientes/{id}               : Actualizar cliente.
- PATCH /clientes/{id}/estado       : Activar/Desactivar cliente (soft-delete).
"""

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.database import get_db
from app.models.sales import Cliente
from app.schemas.sales import ClienteCreate, ClienteUpdate

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ============================================================
# VISTA PRINCIPAL
# ============================================================

@router.get("/clientes", response_class=HTMLResponse)
async def clientes_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "ver")),
):
    """Vista principal de gestión de clientes."""
    # Detectar petición HTMX para evitar duplicar el sidebar
    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="sales/clientes.html",
        context={"usuario": usuario, "base_template": base_template},
    )


# ============================================================
# TABLA DE CLIENTES (HTMX)
# ============================================================

@router.get("/clientes/tabla", response_class=HTMLResponse)
async def tabla_clientes(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "ver")),
    q: str = Query(default="", description="Búsqueda por cédula/RIF o razón social"),
    page: int = Query(default=1, ge=1, description="Número de página"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items por página"),
):
    """
    Devuelve el parcial HTMX con la tabla de clientes paginada y filtrada.
    """
    stmt = select(Cliente)

    # Filtro de texto
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Cliente.cedula_rif.ilike(like),
                Cliente.razon_social.ilike(like),
            )
        )

    # Ordenar por razón social
    stmt = stmt.order_by(Cliente.razon_social)

    # Paginación
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    clientes = db.execute(
        stmt.offset((page - 1) * per_page).limit(per_page)
    ).scalars().all()

    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1

    return templates.TemplateResponse(
        request=request,
        name="sales/_partials/tabla_clientes.html",
        context={
            "clientes": clientes,
            "q": q,
            "page": page,
            "per_page": per_page,
            "total": total or 0,
            "total_pages": total_pages,
            "usuario": usuario,
        },
    )


# ============================================================
# CRUD CLIENTES
# ============================================================

@router.post("/clientes", response_class=JSONResponse)
async def crear_cliente(
    data: ClienteCreate,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "crear")),
):
    """Crea un cliente con validación de Cédula/RIF único."""
    # Validar campos obligatorios
    if not data.cedula_rif.strip() or not data.razon_social.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "Cédula/RIF y Razón Social son obligatorios."},
        )

    # Validar duplicado
    existente = db.scalar(select(Cliente).where(Cliente.cedula_rif == data.cedula_rif))
    if existente:
        return JSONResponse(
            status_code=409,
            content={"error": f"Ya existe un cliente con Cédula/RIF {data.cedula_rif}."},
        )

    cliente = Cliente(
        cedula_rif=data.cedula_rif,
        razon_social=data.razon_social,
        direccion=data.direccion,
        telefono=data.telefono,
        email=data.email,
        limite_credito=data.limite_credito,
        activo=True,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)

    return JSONResponse(
        status_code=201,
        content={
            "ok": True,
            "cliente": {
                "id": cliente.id,
                "cedula_rif": cliente.cedula_rif,
                "razon_social": cliente.razon_social,
            },
        },
    )


@router.put("/clientes/{cliente_id}", response_class=JSONResponse)
async def actualizar_cliente(
    cliente_id: int,
    data: ClienteUpdate,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "editar")),
):
    """Actualiza datos de un cliente con validación de Cédula/RIF duplicado."""
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        return JSONResponse(status_code=404, content={"error": "Cliente no encontrado"})

    # Validar Cédula/RIF duplicado si se está cambiando
    if data.cedula_rif and data.cedula_rif != cliente.cedula_rif:
        existente = db.scalar(
            select(Cliente).where(
                Cliente.cedula_rif == data.cedula_rif,
                Cliente.id != cliente_id,
            )
        )
        if existente:
            return JSONResponse(
                status_code=409,
                content={"error": f"Ya existe un cliente con Cédula/RIF {data.cedula_rif}."},
            )

    # Actualizar solo los campos proporcionados
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(cliente, campo, valor)

    db.commit()
    return JSONResponse(
        status_code=200,
        content={"ok": True, "cliente": {"id": cliente.id, "razon_social": cliente.razon_social}},
    )


@router.patch("/clientes/{cliente_id}/estado", response_class=JSONResponse)
async def cambiar_estado_cliente(
    cliente_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "editar")),
):
    """Activa o desactiva un cliente (soft-delete)."""
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        return JSONResponse(status_code=404, content={"error": "Cliente no encontrado"})

    # Leer el nuevo estado del body/form
    form = await request.form()
    activo = form.get("activo")
    if activo is None:
        return JSONResponse(
            status_code=400,
            content={"error": "El campo 'activo' es obligatorio (true/false)."},
        )

    cliente.activo = activo.lower() in ("true", "1", "on", "yes")
    db.commit()

    return JSONResponse(
        status_code=200,
        content={"ok": True, "id": cliente.id, "activo": cliente.activo},
    )
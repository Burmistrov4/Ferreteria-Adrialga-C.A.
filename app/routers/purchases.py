"""
Router de Compras y Proveedores — Gestión de Compras, Inventario y CxP.

Rutas:
- GET/POST /compras/proveedores      : CRUD proveedores
- GET  /compras                      : Listado de compras
- GET  /compras/tabla                : Parcial HTMX con tabla de compras filtrada
- POST /compras/nueva                : Registrar compra (transacción atómica)
- GET  /compras/{id}/detalle         : Modal HTMX con detalle de compra
- POST /compras/{id}/anular          : Anular compra (reversión inventario y CxP)
- GET  /compras/cxp                  : Cuentas por Pagar
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Integer, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.database import get_db
from app.models.inventory import KardexMovimiento, Producto
from app.models.purchases import Compra, CuentaPorPagar, DetalleCompra, Proveedor
from app.models.sales import TasaRef
from app.models.security import BitacoraAuditoria, Usuario
from app.schemas.purchases import (
    CompraCreate,
    CompraFiltro,
    CompraResponse,
    CuentaPorPagarCreate,
    CuentaPorPagarResponse,
    CuentaPorPagarResumen,
    ProveedorCreate,
    ProveedorResponse,
    ProveedorUpdate,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ============================================================
# PROVEEDORES
# ============================================================

@router.get("/compras/proveedores", response_class=HTMLResponse)
async def proveedores_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("proveedores", "ver")),
):
    """Vista de listado y gestión de proveedores."""
    proveedores = db.execute(
        select(Proveedor).order_by(Proveedor.razon_social)
    ).scalars().all()

    # Detectar petición HTMX para evitar duplicar el sidebar
    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="purchases/proveedores.html",
        context={"usuario": usuario, "proveedores": proveedores, "base_template": base_template},
    )


@router.get("/compras/proveedores/data", response_class=JSONResponse)
async def proveedores_data(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("proveedores", "ver")),
):
    """Devuelve lista de proveedores en JSON para selects/dropdowns."""
    proveedores = db.execute(
        select(Proveedor).order_by(Proveedor.razon_social)
    ).scalars().all()
    return {
        "proveedores": [
            {"id": p.id, "rif": p.rif, "razon_social": p.razon_social}
            for p in proveedores
        ]
    }


@router.post("/compras/proveedores", response_class=JSONResponse)
async def proveedor_crear(
    data: ProveedorCreate,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("proveedores", "crear")),
):
    """Crea un proveedor nuevo."""
    existente = db.scalar(select(Proveedor).where(Proveedor.rif == data.rif))
    if existente:
        return JSONResponse(
            status_code=400,
            content={"error": f"Ya existe un proveedor con RIF {data.rif}"},
        )

    proveedor = Proveedor(**data.model_dump())
    db.add(proveedor)
    db.flush()

    return JSONResponse(
        status_code=201,
        content={
            "ok": True,
            "proveedor": {
                "id": proveedor.id,
                "rif": proveedor.rif,
                "razon_social": proveedor.razon_social,
            },
        },
    )


@router.put("/compras/proveedores/{proveedor_id}", response_class=JSONResponse)
async def proveedor_editar(
    proveedor_id: int,
    data: ProveedorUpdate,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("proveedores", "editar")),
):
    """Actualiza datos de un proveedor con validación de RIF duplicado."""
    proveedor = db.get(Proveedor, proveedor_id)
    if not proveedor:
        return JSONResponse(status_code=404, content={"error": "Proveedor no encontrado"})

    # Validar RIF duplicado si se está cambiando
    if data.rif and data.rif != proveedor.rif:
        existente = db.scalar(
            select(Proveedor).where(Proveedor.rif == data.rif, Proveedor.id != proveedor_id)
        )
        if existente:
            return JSONResponse(
                status_code=409,
                content={"error": f"Ya existe un proveedor con RIF {data.rif}."},
            )

    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(proveedor, campo, valor)

    db.commit()
    return JSONResponse(
        status_code=200,
        content={"ok": True, "proveedor": {"id": proveedor.id, "razon_social": proveedor.razon_social}},
    )


@router.delete("/compras/proveedores/{proveedor_id}", response_class=JSONResponse)
async def desactivar_proveedor(
    proveedor_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("proveedores", "editar")),
):
    """Desactiva (soft-delete) un proveedor."""
    proveedor = db.get(Proveedor, proveedor_id)
    if not proveedor:
        return JSONResponse(status_code=404, content={"error": "Proveedor no encontrado"})

    proveedor.activo = False
    db.commit()
    return JSONResponse(status_code=200, content={"ok": True})


# ============================================================
# COMPRAS
# ============================================================

@router.get("/compras", response_class=HTMLResponse)
async def compras_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("compras", "ver")),
    q: str = Query(default="", description="Búsqueda por proveedor o número de control"),
    page: int = Query(default=1, ge=1, description="Número de página"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items por página"),
):
    """Vista principal de compras."""
    # Detectar petición HTMX para evitar duplicar el sidebar
    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    # Cargar compras iniciales (server-side rendering)
    stmt = (
        select(Compra, Proveedor, Usuario)
        .join(Proveedor, Compra.proveedor_id == Proveedor.id)
        .join(Usuario, Compra.usuario_id == Usuario.id)
    )
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Proveedor.razon_social.ilike(like),
                Proveedor.rif.ilike(like),
                Compra.numero_control.ilike(like),
            )
        )
    stmt = stmt.order_by(Compra.fecha_compra.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.execute(
        stmt.offset((page - 1) * per_page).limit(per_page)
    ).all()

    compras = []
    for compra, proveedor, usr in items:
        compras.append(
            {
                "id": compra.id,
                "numero_control": compra.numero_control,
                "proveedor_razon": proveedor.razon_social,
                "proveedor_rif": proveedor.rif,
                "fecha_compra": compra.fecha_compra.strftime("%d/%m/%Y %H:%M"),
                "estado": compra.estado,
                "total_bs": compra.total_bs,
                "usuario_nombre": usr.nombre_completo,
            }
        )
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1

    return templates.TemplateResponse(
        request=request,
        name="purchases/compras.html",
        context={
            "usuario": usuario,
            "base_template": base_template,
            "q": q,
            "compras": compras,
            "page": page,
            "per_page": per_page,
            "total": total or 0,
            "total_pages": total_pages,
        },
    )


@router.get("/compras/tabla", response_class=HTMLResponse)
async def compras_tabla(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("compras", "ver")),
    q: str = Query(default="", description="Búsqueda por proveedor o número de control"),
    page: int = Query(default=1, ge=1, description="Número de página"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items por página"),
):
    """
    Devuelve el parcial HTMX con la tabla de compras paginada y filtrada.

    Parámetros:
    - q: búsqueda en nombre de proveedor, RIF o número de control.
    - page / per_page: paginación.
    """
    stmt = (
        select(Compra, Proveedor, Usuario)
        .join(Proveedor, Compra.proveedor_id == Proveedor.id)
        .join(Usuario, Compra.usuario_id == Usuario.id)
    )

    # Filtro de texto
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Proveedor.razon_social.ilike(like),
                Proveedor.rif.ilike(like),
                Compra.numero_control.ilike(like),
            )
        )

    # Ordenar por fecha descendente
    stmt = stmt.order_by(Compra.fecha_compra.desc())

    # Paginación
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.execute(
        stmt.offset((page - 1) * per_page).limit(per_page)
    ).all()

    compras = []
    for compra, proveedor, usr in items:
        compras.append(
            {
                "id": compra.id,
                "numero_control": compra.numero_control,
                "proveedor_razon": proveedor.razon_social,
                "proveedor_rif": proveedor.rif,
                "fecha_compra": compra.fecha_compra.strftime("%d/%m/%Y %H:%M"),
                "estado": compra.estado,
                "total_bs": compra.total_bs,
                "usuario_nombre": usr.nombre_completo,
            }
        )

    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1

    return templates.TemplateResponse(
        request=request,
        name="purchases/_partials/tabla_compras.html",
        context={
            "compras": compras,
            "q": q,
            "page": page,
            "per_page": per_page,
            "total": total or 0,
            "total_pages": total_pages,
            "usuario": usuario,
        },
    )


@router.post("/compras/nueva", response_class=JSONResponse)
async def crear_compra(
    data: CompraCreate,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("compras", "crear")),
):
    """
    Registra una compra nueva (transacción atómica).

    Pasos:
    1. Valida proveedor y número de control.
    2. Inserta cabecera y detalles.
    3. Actualiza stock y costo de productos.
    4. Genera movimientos Kardex ENTRADA.
    5. Crea Cuenta por Pagar si es a crédito.
    """
    try:
        # 1. Validar proveedor
        proveedor = db.get(Proveedor, data.proveedor_id)
        if not proveedor:
            db.rollback()
            return JSONResponse(
                status_code=400,
                content={"error": "Proveedor no válido"},
            )

        # Validar número de control único
        existe = db.scalar(
            select(Compra).where(Compra.numero_control == data.numero_control)
        )
        if existe:
            db.rollback()
            return JSONResponse(
                status_code=400,
                content={"error": f"Ya existe una compra con número {data.numero_control}"},
            )

        # 2. Obtener tasa REF para conversión
        tasa_ref = db.scalar(select(TasaRef).order_by(TasaRef.fecha.desc()).limit(1))
        if not tasa_ref:
            db.rollback()
            return JSONResponse(
                status_code=400,
                content={"error": "No hay tasa de cambio registrada."},
            )

        # 3. Crear cabecera de compra
        compra = Compra(
            proveedor_id=data.proveedor_id,
            usuario_id=usuario.id,
            numero_control=data.numero_control,
            subtotal_bs=data.subtotal_bs,
            iva_bs=data.iva_bs,
            total_bs=data.total_bs,
        )
        db.add(compra)
        db.flush()

        # 4. Procesar detalles
        for detalle_data in data.detalles:
            producto = db.get(Producto, detalle_data.producto_id)
            if not producto:
                raise ValueError(f"Producto {detalle_data.producto_id} no existe")

            # Crear detalle
            detalle = DetalleCompra(
                compra_id=compra.id,
                producto_id=detalle_data.producto_id,
                cantidad=detalle_data.cantidad,
                costo_unitario_bs=detalle_data.costo_unitario_bs,
            )
            db.add(detalle)

            # Actualizar stock y costo
            producto.stock_actual += detalle_data.cantidad
            # Actualizar costo de referencia (simple: último costo)
            producto.precio_ref = detalle_data.costo_unitario_bs

            # Kardex ENTRADA
            kardex = KardexMovimiento(
                producto_id=producto.id,
                tipo_movimiento="ENTRADA",
                cantidad=detalle_data.cantidad,
                costo_ref=detalle_data.costo_unitario_bs,
                origen_id=compra.id,
                fecha=datetime.now(timezone.utc),
            )
            db.add(kardex)

        # 5. Cuenta por Pagar si es a crédito
        if data.forma_pago == "CREDITO":
            fecha_venc = date.today()
            if data.dias_credito and data.dias_credito > 0:
                from datetime import timedelta
                fecha_venc = date.today() + timedelta(days=data.dias_credito)

            cxp = CuentaPorPagar(
                compra_id=compra.id,
                proveedor_id=proveedor.id,
                monto_total_bs=data.total_bs,
                saldo_pendiente_bs=data.total_bs,
                fecha_vencimiento=fecha_venc,
            )
            db.add(cxp)

        db.commit()

        return JSONResponse(
            status_code=201,
            content={
                "ok": True,
                "compra_id": compra.id,
                "numero_control": compra.numero_control,
                "total_bs": float(compra.total_bs),
            },
        )

    except ValueError as e:
        db.rollback()
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        db.rollback()
        return JSONResponse(
            status_code=500,
            content={"error": f"Error al procesar compra: {str(e)}"},
        )


@router.get("/compras/cxp", response_class=HTMLResponse)
async def cxp_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("compras", "ver")),
):
    """Vista de Cuentas por Pagar."""
    # Detectar petición HTMX para evitar duplicar el sidebar
    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="purchases/cxp.html",
        context={"usuario": usuario, "base_template": base_template},
    )


@router.get("/compras/cxp/data", response_class=JSONResponse)
async def cxp_data(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("compras", "ver")),
    proveedor_id: Optional[int] = Query(default=None),
):
    """Consulta de CxP con resumen por proveedor."""
    stmt = (
        select(
            Proveedor.id,
            Proveedor.razon_social,
            func.count(CuentaPorPagar.id).label("cantidad_deudas"),
            func.sum(CuentaPorPagar.monto_total_bs).label("monto_total"),
            func.sum(CuentaPorPagar.saldo_pendiente_bs).label("saldo_pendiente"),
            func.sum(
                func.cast(
                    func.julianday(CuentaPorPagar.fecha_vencimiento) - func.julianday(date.today()),
                    Integer,
                )
            ).label("dias_promedio"),
        )
        .join(CuentaPorPagar, Proveedor.id == CuentaPorPagar.proveedor_id)
        .group_by(Proveedor.id, Proveedor.razon_social)
    )

    if proveedor_id:
        stmt = stmt.where(Proveedor.id == proveedor_id)

    resultados = db.execute(stmt).all()

    resumenes = []
    for prov_id, razon, cantidad, monto_total, saldo_pend, dias_prom in resultados:
        # Calcular vencidas (simplificado: saldo > 0 y fecha vencida)
        vencidas = db.scalar(
            select(func.count(CuentaPorPagar.id))
            .where(
                CuentaPorPagar.proveedor_id == prov_id,
                CuentaPorPagar.saldo_pendiente_bs > 0,
                CuentaPorPagar.fecha_vencimiento < date.today(),
            )
        ) or 0

        resumenes.append(
            CuentaPorPagarResumen(
                proveedor_id=prov_id,
                proveedor_nombre=razon,
                cantidad_deudas=cantidad or 0,
                monto_total=monto_total or Decimal("0.00"),
                saldo_pendiente=saldo_pend or Decimal("0.00"),
                vencidas=vencidas,
            )
        )

    return {"resumenes": [r.model_dump() for r in resumenes]}


@router.post("/compras/cxp/{cxp_id}/abonar", response_class=JSONResponse)
async def abonar_cxp(
    cxp_id: int,
    monto: float,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("compras", "editar")),
):
    """Registra un abono a una cuenta por pagar."""
    cxp = db.get(CuentaPorPagar, cxp_id)
    if not cxp:
        return JSONResponse(status_code=404, content={"error": "CxP no encontrada"})

    monto_bs = Decimal(str(monto))
    if monto_bs <= 0:
        return JSONResponse(status_code=400, content={"error": "Monto inválido"})

    if monto_bs > cxp.saldo_pendiente_bs:
        return JSONResponse(
            status_code=400,
            content={"error": f"Monto excede saldo pendiente (Bs {cxp.saldo_pendiente_bs:.2f})"},
        )

    cxp.saldo_pendiente_bs -= monto_bs

    # El estado se determina por el saldo pendiente (no existe campo 'estado' en el modelo)
    # Si el saldo llega a 0, la CxP queda saldada automáticamente.

    db.flush()

    estado = "SALDADA" if cxp.saldo_pendiente_bs == 0 else "PENDIENTE"
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "nuevo_saldo": float(cxp.saldo_pendiente_bs),
            "estado": estado,
        },
    )


# ============================================================
# DETALLE DE COMPRA
# ============================================================

@router.get("/compras/{compra_id}/detalle", response_class=HTMLResponse)
async def detalle_compra(
    compra_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("compras", "ver")),
):
    """Vista del detalle de una compra con modal HTMX."""
    compra = db.get(Compra, compra_id)
    if not compra:
        return JSONResponse(status_code=404, content={"error": "Compra no encontrada"})

    # Datos del proveedor
    proveedor = db.get(Proveedor, compra.proveedor_id)

    # Detalles de la compra con productos (usar .all() para obtener tuples (DetalleCompra, Producto))
    detalles = db.execute(
        select(DetalleCompra, Producto)
        .join(Producto, DetalleCompra.producto_id == Producto.id)
        .where(DetalleCompra.compra_id == compra_id)
    ).all()

    # Datos del usuario que registró la compra
    usr = db.get(Usuario, compra.usuario_id)

    # Datos de la CxP asociada
    cxp = db.scalar(select(CuentaPorPagar).where(CuentaPorPagar.compra_id == compra_id))

    return templates.TemplateResponse(
        request=request,
        name="purchases/_partials/modal_detalle_compra.html",
        context={
            "usuario": usuario,
            "compra": compra,
            "proveedor": proveedor,
            "usr": usr,
            "detalles": detalles,
            "cxp": cxp,
        },
    )


# ============================================================
# ANULAR COMPRA
# ============================================================

@router.post("/compras/{compra_id}/anular", response_class=JSONResponse)
async def anular_compra(
    compra_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("compras", "editar")),
):
    """Anula una compra dentro de una transacción atómica."""
    compra = db.get(Compra, compra_id)
    if not compra:
        return JSONResponse(status_code=404, content={"error": "Compra no encontrada"})

    # Comprobar que no esté anulada previamente
    if compra.estado == "ANULADA":
        return JSONResponse(
            status_code=400,
            content={"error": "La compra ya ha sido anulada previamente."},
        )

    try:
        # 1. Disminuir stock_actual de cada producto en detalle_compras
        for detalle in compra.detalles:
            producto = db.get(Producto, detalle.producto_id)
            if producto:
                producto.stock_actual -= detalle.cantidad

                # Registrar movimiento Kardex SALIDA por anulación
                kardex = KardexMovimiento(
                    producto_id=producto.id,
                    tipo_movimiento="SALIDA",
                    cantidad=detalle.cantidad,
                    costo_ref=detalle.costo_unitario_bs,
                    origen_id=compra.id,
                    fecha=datetime.now(timezone.utc),
                )
                db.add(kardex)

        # 2. Ajustar/cancelar la CxP asociada
        cxp = db.scalar(select(CuentaPorPagar).where(CuentaPorPagar.compra_id == compra_id))
        if cxp:
            cxp.saldo_pendiente_bs = Decimal("0.00")

        # 3. Cambiar estado de la compra a ANULADA
        compra.estado = "ANULADA"

        # 4. Registrar en bitácora de auditoría
        bitacora = BitacoraAuditoria(
            usuario_id=usuario.id,
            modulo="compras",
            accion="anular_compra",
            detalles=f"Compra {compra.numero_control} anulada, stock reducido, CxP cancelada",
            ip_address="127.0.0.1",  # En producción obtener IP real
        )
        db.add(bitacora)

        db.commit()

    except Exception as e:
        db.rollback()
        return JSONResponse(
            status_code=500,
            content={"error": f"Error al anular compra: {str(e)}"},
        )

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "compra_id": compra.id,
            "numero_control": compra.numero_control,
            "mensaje": "Compra anulada exitosamente",
        },
    )

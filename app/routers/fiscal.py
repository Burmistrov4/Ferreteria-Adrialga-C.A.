"""
Router Fiscal — Cierre Z, Libro de Ventas y Declaración IVA.

Rutas:
- GET  /fiscal/cierre-z           : Vista principal del módulo fiscal y listado de cierres.
- POST /fiscal/cierre-z/generar   : Genera Cierre Z (transacción atómica).
- GET  /fiscal/libro-ventas       : Consulta paginada del Libro de Ventas.
- POST /fiscal/caja/abrir         : Abre sesión de caja para el cajero actual.
- GET  /fiscal/caja/reporte-x     : Obtiene el Reporte X de la caja activa.
- POST /fiscal/caja/cerrar        : Genera el cierre de caja (Reporte Z).
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.database import get_db
from app.models.cash import CierreCaja, SesionCaja
from app.models.fiscal import CierreZ, RetencionISLR, RetencionIVA
from app.models.purchases import Compra, DetalleCompra, Proveedor
from app.models.sales import Cliente, DetalleVenta, Factura, FormaPago, PagoVenta, TasaRef
from app.schemas.fiscal import (
    CajaAperturaCreate,
    CierreCajaCreate,
    CierreCajaResponse,
    CierreZCreate,
    CierreZResponse,
    CierreZResumen,
    LibroComprasItem,
    LibroComprasResumen,
    LibroVentasFiltro,
    LibroVentasItem,
    LibroVentasResumen,
    ReporteXResponse,
    RetencionIVACreate,
    RetencionIVAResponse,
    RetencionISLRCreate,
    RetencionISLRResponse,
)
from app.services.fiscal_service import (
    calculate_reporte_x,
    close_caja,
    get_active_caja,
    get_current_tasa_ref,
    open_caja,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ============================================================
# VISTAS
# ============================================================
@router.get("/fiscal/cierre-z", response_class=HTMLResponse)
async def cierre_z_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("fiscal", "ver")),
):
    """Vista principal del módulo fiscal y listado de cierres pasados."""
    cierres = db.execute(
        select(CierreCaja).order_by(CierreCaja.fecha_hora.desc()).limit(20)
    ).scalars().all()

    # Detectar petición HTMX para evitar duplicar el sidebar
    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="fiscal/cierre_z.html",
        context={
            "usuario": usuario,
            "cierres": cierres,
            "base_template": base_template,
        },
    )


@router.get("/fiscal/libro-ventas", response_class=HTMLResponse)
async def libro_ventas_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("fiscal", "ver")),
):
    """Vista del Libro de Ventas."""
    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="fiscal/libro_ventas.html",
        context={
            "usuario": usuario,
            "base_template": base_template,
            "current_year": datetime.now().year,
        },
    )


@router.get("/fiscal/libro-compras", response_class=HTMLResponse)
async def libro_compras_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("fiscal", "ver")),
):
    """Vista del Libro de Compras."""
    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="fiscal/libro_compras.html",
        context={
            "usuario": usuario,
            "base_template": base_template,
            "current_year": datetime.now().year,
        },
    )


# ============================================================
# API - CAJA
# ============================================================
@router.post("/fiscal/caja/abrir", response_class=JSONResponse)
async def abrir_caja(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("fiscal", "crear")),
):
    """Abre una sesión de caja para el cajero actual."""
    try:
        payload = await request.json()
        caja_data = CajaAperturaCreate(**payload)
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": f"Datos inválidos: {exc}"})

    try:
        tasa = get_current_tasa_ref(db)
        with db.begin():
            caja = open_caja(
                db=db,
                usuario_id=usuario.id,
                monto_inicial_bs=caja_data.monto_inicial_bs,
                monto_inicial_usd=caja_data.monto_inicial_usd,
                tasa_ref_monto=tasa.monto_bs,
            )
        return JSONResponse(
            status_code=201,
            content={
                "ok": True,
                "caja": {
                    "id": caja.id,
                    "usuario_id": caja.usuario_id,
                    "fecha_apertura": caja.fecha_apertura.isoformat(),
                    "monto_inicial_bs": float(caja.monto_inicial_bs),
                    "monto_inicial_usd": float(caja.monto_inicial_usd),
                    "tasa_ref_monto": float(caja.tasa_ref_monto),
                    "estado": caja.estado,
                },
            },
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@router.get("/fiscal/caja/reporte-x", response_class=JSONResponse)
async def reporte_x(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("fiscal", "ver")),
):
    """Consulta los totales acumulados para la sesión de caja abierta."""
    caja = get_active_caja(db, usuario.id)
    if not caja:
        return JSONResponse(
            status_code=400,
            content={"error": "No hay sesión de caja abierta para este usuario."},
        )
    reporte = calculate_reporte_x(db, caja.id)
    return JSONResponse(status_code=200, content={"ok": True, "reporte_x": {
        "total_ventas_bs": float(reporte["total_ventas_bs"]),
        "total_ventas_usd": float(reporte["total_ventas_usd"]),
        "total_iva_bs": float(reporte["total_iva_bs"]),
        "total_igtf_bs": float(reporte["total_igtf_bs"]),
        "total_efectivo_bs": float(reporte["total_efectivo_bs"]),
        "total_efectivo_usd": float(reporte["total_efectivo_usd"]),
        "total_pago_movil": float(reporte["total_pago_movil"]),
        "total_punto_de_venta": float(reporte["total_punto_de_venta"]),
        "total_transferencia": float(reporte["total_transferencia"]),
    }})


@router.post("/fiscal/caja/cerrar", response_class=JSONResponse)
async def cerrar_caja(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("fiscal", "crear")),
):
    """Cierra la sesión de caja activa y genera el Reporte Z."""
    try:
        payload = await request.json()
        cierre_data = CierreCajaCreate(**payload)
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": f"Datos inválidos: {exc}"})

    caja = get_active_caja(db, usuario.id)
    if not caja:
        return JSONResponse(
            status_code=400,
            content={"error": "No hay sesión de caja abierta para este usuario."},
        )

    try:
        with db.begin():
            cierre = close_caja(
                db=db,
                sesion_id=caja.id,
                efectivo_bs=cierre_data.efectivo_bs,
                efectivo_usd=cierre_data.efectivo_usd,
                pago_movil=cierre_data.pago_movil,
                punto_venta=cierre_data.punto_venta,
                transferencia=cierre_data.transferencia,
            )
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "cierre_id": cierre.id,
                "numero_reporte_z": cierre.numero_reporte_z,
                "fecha_hora": cierre.fecha_hora.isoformat(),
                "total_ventas_bs": float(cierre.total_ventas_bs),
                "total_ventas_usd": float(cierre.total_ventas_usd),
                "total_iva_bs": float(cierre.total_iva_bs),
                "total_igtf_bs": float(cierre.total_igtf_bs),
                "total_efectivo_bs": float(cierre.total_efectivo_bs),
                "total_efectivo_usd": float(cierre.total_efectivo_usd),
                "total_pago_movil": float(cierre.total_pago_movil),
                "total_punto_de_venta": float(cierre.total_punto_de_venta),
                "total_transferencia": float(cierre.total_transferencia),
                "diferencia_sobrante_faltante": float(
                    cierre.diferencia_sobrante_faltante
                ),
                "factura_inicio": cierre.factura_inicio,
                "factura_fin": cierre.factura_fin,
                "cantidad_operaciones": cierre.cantidad_operaciones,
            },
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


# ============================================================
# API - GENERAR CIERRE Z
# ============================================================
@router.post("/fiscal/cierre-z/generar", response_class=JSONResponse)
async def generar_cierre_z(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("fiscal", "crear")),
):
    """
    Genera un Cierre Z (transacción atómica).

    Agrupa todas las facturas emitidas desde el último Cierre Z
    (o desde el inicio del día) y calcula totales fiscales.
    """
    with db.begin():
        ultimo_cierre = db.scalar(select(CierreZ).order_by(CierreZ.fecha.desc()).limit(1))
        ahora = datetime.now(timezone.utc)
        if ultimo_cierre:
            fecha_desde = ultimo_cierre.fecha
        else:
            fecha_desde = datetime(ahora.year, ahora.month, ahora.day, tzinfo=timezone.utc)

        stmt = (
            select(Factura)
            .where(
                and_(
                    Factura.fecha_emision >= fecha_desde,
                    Factura.estado == "EMITIDA",
                )
            )
            .order_by(Factura.fecha_emision)
        )

        facturas = db.execute(stmt).scalars().all()

        if not facturas:
            return JSONResponse(
                status_code=400,
                content={"error": "No hay facturas emitidas en el rango seleccionado."},
            )

        total_ventas_bs = Decimal("0.00")
        total_iva_bs = Decimal("0.00")
        total_igtf_bs = Decimal("0.00")

        for factura in facturas:
            total_ventas_bs += factura.total_bs
            total_iva_bs += factura.iva_bs
            total_igtf_bs += factura.igtf_bs

        cierre = CierreZ(
            usuario_id=usuario.id,
            fecha=ahora,
            total_ventas_bs=total_ventas_bs.quantize(Decimal("0.00")),
            total_iva_bs=total_iva_bs.quantize(Decimal("0.00")),
            total_igtf_bs=total_igtf_bs.quantize(Decimal("0.00")),
            factura_inicio=facturas[0].numero_factura,
            factura_fin=facturas[-1].numero_factura,
            cantidad_operaciones=len(facturas),
        )
        db.add(cierre)
        db.flush()

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "cierre_id": cierre.id,
            "fecha": cierre.fecha.isoformat(),
            "total_ventas_bs": float(cierre.total_ventas_bs),
            "total_iva_bs": float(cierre.total_iva_bs),
            "total_igtf_bs": float(cierre.total_igtf_bs),
            "cantidad_operaciones": cierre.cantidad_operaciones,
            "factura_inicio": cierre.factura_inicio,
            "factura_fin": cierre.factura_fin,
        },
    )


# ============================================================
# API - LIBRO DE VENTAS
# ============================================================
@router.get("/fiscal/libro-ventas/data", response_class=JSONResponse)
async def libro_ventas_data(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("fiscal", "ver")),
    fecha_desde: Optional[date] = Query(default=None),
    fecha_hasta: Optional[date] = Query(default=None),
    mes: Optional[int] = Query(default=None, ge=1, le=12),
    anio: Optional[int] = Query(default=None, ge=2000),
):
    """
    Consulta paginada y filtrable del Libro de Ventas.

    Retorna estructura conforme a normativa SENIAT.
    """
    filtros = [Factura.estado == "EMITIDA"]

    if mes and anio:
        filtros.append(
            and_(
                func.extract("month", Factura.fecha_emision) == mes,
                func.extract("year", Factura.fecha_emision) == anio,
            )
        )
    elif fecha_desde and fecha_hasta:
        filtros.append(
            and_(
                Factura.fecha_emision >= fecha_desde,
                Factura.fecha_emision <= fecha_hasta,
            )
        )

    stmt = (
        select(
            Factura,
            Cliente,
            func.sum(DetalleVenta.cantidad * DetalleVenta.precio_unitario_bs).label(
                "base_imponible"
            ),
            func.sum(DetalleVenta.total_linea_bs).label("total_con_iva"),
        )
        .join(Cliente, Factura.cliente_id == Cliente.id)
        .join(DetalleVenta, Factura.id == DetalleVenta.factura_id)
        .where(and_(*filtros))
        .group_by(Factura.id, Cliente.id)
        .order_by(Factura.fecha_emision)
    )

    resultados = db.execute(stmt).all()

    items = []
    total_base = Decimal("0.00")
    total_iva = Decimal("0.00")
    total_ventas = Decimal("0.00")

    for factura, cliente, base_imponible, total_con_iva in resultados:
        iva = total_con_iva - base_imponible if total_con_iva and base_imponible else Decimal("0.00")

        items.append(
            LibroVentasItem(
                rif=cliente.cedula_rif,
                razon_social=cliente.razon_social,
                numero_factura=factura.numero_factura,
                numero_control=factura.numero_factura,
                fecha_emision=factura.fecha_emision.date(),
                base_imponible=base_imponible.quantize(Decimal("0.00"))
                if base_imponible
                else Decimal("0.00"),
                porcentaje_iva=Decimal("16.00"),
                monto_iva=iva.quantize(Decimal("0.00")),
                total_con_iva=total_con_iva.quantize(Decimal("0.00"))
                if total_con_iva
                else Decimal("0.00"),
            )
        )

        total_base += base_imponible if base_imponible else Decimal("0.00")
        total_iva += iva
        total_ventas += total_con_iva if total_con_iva else Decimal("0.00")

    resumen = LibroVentasResumen(
        periodo_mes=mes or (fecha_desde.month if fecha_desde else date.today().month),
        periodo_anio=anio or (fecha_desde.year if fecha_desde else date.today().year),
        total_operaciones=len(items),
        total_base_imponible=total_base.quantize(Decimal("0.00")),
        total_iva=total_iva.quantize(Decimal("0.00")),
        total_ventas=total_ventas.quantize(Decimal("0.00")),
        detalle=items,
    )

    return resumen


# ============================================================
# LIBRO DE COMPRAS
# ============================================================
@router.get("/fiscal/libro-compras/data", response_class=JSONResponse)
async def libro_compras_data(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("fiscal", "ver")),
    fecha_desde: Optional[date] = Query(default=None),
    fecha_hasta: Optional[date] = Query(default=None),
    mes: Optional[int] = Query(default=None, ge=1, le=12),
    anio: Optional[int] = Query(default=None, ge=2000),
):
    """
    Consulta del Libro de Compras.

    Retorna estructura conforme a normativa SENIAT.
    """
    filtros = []
    if mes and anio:
        filtros.append(
            and_(
                func.extract("month", Compra.fecha_compra) == mes,
                func.extract("year", Compra.fecha_compra) == anio,
            )
        )
    elif fecha_desde and fecha_hasta:
        filtros.append(
            and_(
                Compra.fecha_compra >= fecha_desde,
                Compra.fecha_compra <= fecha_hasta,
            )
        )

    stmt = (
        select(
            Compra,
            Proveedor,
            DetalleCompra,
            RetencionIVA.numero_comprobante.label("retencion_numero"),
            RetencionIVA.monto_retenido.label("iva_retenido"),
        )
        .join(Proveedor, Compra.proveedor_id == Proveedor.id)
        .join(DetalleCompra, Compra.id == DetalleCompra.compra_id)
        .outerjoin(RetencionIVA, Compra.id == RetencionIVA.compra_id)
        .where(and_(*filtros))
        .order_by(Compra.fecha_compra)
    )

    resultados = db.execute(stmt).all()

    items = []
    total_base = Decimal("0.00")
    total_iva = Decimal("0.00")
    total_iva_retenido = Decimal("0.00")
    total_compras = Decimal("0.00")

    for compra, proveedor, detalle, ret_num, iva_ret in resultados:
        base = detalle.costo_unitario_bs * detalle.cantidad
        iva = base * Decimal("0.16")

        items.append(
            LibroComprasItem(
                fecha_compra=compra.fecha_compra.date(),
                rif_proveedor=proveedor.rif,
                razon_social=proveedor.razon_social,
                numero_factura=compra.numero_control,
                numero_control=compra.numero_control,
                total_compra=compra.total_bs,
                base_imponible=base.quantize(Decimal("0.00")),
                porcentaje_iva=Decimal("16.00"),
                monto_iva=iva.quantize(Decimal("0.00")),
                iva_retenido=iva_ret.quantize(Decimal("0.00")) if iva_ret else Decimal("0.00"),
                numero_comprobante_retencion=ret_num,
            )
        )

        total_base += base
        total_iva += iva
        total_iva_retenido += iva_ret if iva_ret else Decimal("0.00")
        total_compras += compra.total_bs

    resumen = LibroComprasResumen(
        periodo_mes=mes or (fecha_desde.month if fecha_desde else date.today().month),
        periodo_anio=anio or (fecha_desde.year if fecha_desde else date.today().year),
        total_operaciones=len(items),
        total_base_imponible=total_base.quantize(Decimal("0.00")),
        total_iva=total_iva.quantize(Decimal("0.00")),
        total_iva_retenido=total_iva_retenido.quantize(Decimal("0.00")),
        total_compras=total_compras.quantize(Decimal("0.00")),
        detalle=items,
    )

    return resumen


# ============================================================
# RETENCIONES
# ============================================================
@router.post("/compras/{compra_id}/generar-retencion-iva", response_class=JSONResponse)
async def generar_retencion_iva(
    compra_id: int,
    data: RetencionIVACreate,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("fiscal", "crear")),
):
    """Genera retención de IVA para una compra."""
    compra = db.get(Compra, compra_id)
    if not compra:
        return JSONResponse(status_code=404, content={"error": "Compra no encontrada"})

    existe = db.scalar(select(RetencionIVA).where(RetencionIVA.compra_id == compra_id))
    if existe:
        return JSONResponse(
            status_code=400,
            content={"error": "Ya existe una retención de IVA para esta compra"},
        )

    año = datetime.now().year
    mes = datetime.now().month
    ultimo = db.scalar(
        select(func.count(RetencionIVA.id)).where(
            func.extract("year", RetencionIVA.fecha_retencion) == año,
            func.extract("month", RetencionIVA.fecha_retencion) == mes,
        )
    ) or 0
    numero_comprobante = f"{año}{mes:02d}{ultimo + 1:06d}"

    retencion = RetencionIVA(
        compra_id=compra_id,
        numero_comprobante=numero_comprobante,
        base_imponible=data.base_imponible,
        porcentaje_retencion=data.porcentaje_retencion,
        monto_retenido=data.monto_retenido,
    )
    db.add(retencion)
    db.flush()

    return JSONResponse(
        status_code=201,
        content={
            "ok": True,
            "retencion_id": retencion.id,
            "numero_comprobante": retencion.numero_comprobante,
        },
    )


@router.post("/compras/{compra_id}/generar-retencion-islr", response_class=JSONResponse)
async def generar_retencion_islr(
    compra_id: int,
    data: RetencionISLRCreate,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("fiscal", "crear")),
):
    """Genera retención de ISLR para una compra."""
    compra = db.get(Compra, compra_id)
    if not compra:
        return JSONResponse(status_code=404, content={"error": "Compra no encontrada"})

    existe = db.scalar(select(RetencionISLR).where(RetencionISLR.compra_id == compra_id))
    if existe:
        return JSONResponse(
            status_code=400,
            content={"error": "Ya existe una retención de ISLR para esta compra"},
        )

    año = datetime.now().year
    mes = datetime.now().month
    ultimo = db.scalar(
        select(func.count(RetencionISLR.id)).where(
            func.extract("year", RetencionISLR.fecha_retencion) == año,
            func.extract("month", RetencionISLR.fecha_retencion) == mes,
        )
    ) or 0
    numero_comprobante = f"{año}{mes:02d}{ultimo + 1:06d}"

    retencion = RetencionISLR(
        compra_id=compra_id,
        numero_comprobante=numero_comprobante,
        concepto=data.concepto,
        base_imponible=data.base_imponible,
        porcentaje_retencion=data.porcentaje_retencion,
        sustraendo=data.sustraendo,
        monto_retenido=data.monto_retenido,
    )
    db.add(retencion)
    db.flush()

    return JSONResponse(
        status_code=201,
        content={
            "ok": True,
            "retencion_id": retencion.id,
            "numero_comprobante": retencion.numero_comprobante,
        },
    )


@router.get("/compras/retencion/{retencion_id}", response_class=HTMLResponse)
async def ver_comprobante_retencion(
    retencion_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("fiscal", "ver")),
):
    """Vista del comprobante de retención (IVA o ISLR)."""
    retencion_iva = db.scalar(
        select(RetencionIVA).where(RetencionIVA.id == retencion_id)
    )
    retencion_islr = db.scalar(
        select(RetencionISLR).where(RetencionISLR.id == retencion_id)
    )

    if retencion_iva:
        retencion = retencion_iva
        tipo = "IVA"
    elif retencion_islr:
        retencion = retencion_islr
        tipo = "ISLR"
    else:
        return HTMLResponse(content="<h1>Retención no encontrada</h1>", status_code=404)

    compra = db.get(Compra, retencion.compra_id)
    proveedor = db.get(Proveedor, compra.proveedor_id)

    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="purchases/comprobante_retencion.html",
        context={
            "usuario": usuario,
            "retencion": retencion,
            "tipo": tipo,
            "compra": compra,
            "proveedor": proveedor,
            "base_template": base_template,
        },
    )
"""
Router del Dashboard Principal — Vista de métricas del sistema.

Rutas:
- GET /                    : Panel de control principal
- GET /grafico-ventas      : Datos para gráficos de ventas
- GET /auditoria           : Bitácora de auditoría
- GET /reportes/mas-vendidos : Top 10 productos más vendidos
- GET /reportes/rentabilidad : Rentabilidad por producto
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.database import get_db
from app.models import (
    BitacoraAuditoria,
    Categoria,
    CierreZ,
    CuentaPorCobrar,
    CuentaPorPagar,
    DetalleCompra,
    DetalleVenta,
    Factura,
    PagoVenta,
    Producto,
    TasaRef,
    Usuario,
)
from app.schemas.dashboard import (
    AlertaStock,
    BitacoraFiltro,
    BitacoraItem,
    BitacoraResumen,
    DashboardKPIs,
    ProductoMasVendido,
    RentabilidadProducto,
    ReporteVentasResumen,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _formatear_bs(monto: Decimal | int | float) -> str:
    """Formatea un monto en Bolívares con separadores de miles."""
    return f"{float(monto):,.2f}"


# ============================================================
# DASHBOARD PRINCIPAL
# ============================================================

@router.get("/", response_class=HTMLResponse, name="dashboard")
def dashboard(
    request: Request,
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """
    Renderiza el panel de control principal.
    """
    # Métricas
    kpis = _obtener_kpis(db)
    
    # Productos bajo stock
    productos_bajo_stock = db.scalars(
        select(Producto).where(
            Producto.activo.is_(True),
            Producto.stock_actual <= Producto.stock_minimo,
        )
    ).all()
    
    # Último cierre Z
    ultimo_cierre = db.scalar(select(CierreZ).order_by(CierreZ.fecha.desc()).limit(1))
    
    # Datos para gráficos (últimos 30 días)
    datos_grafico = _datos_grafico_ventas(db)

    return templates.TemplateResponse(
        request=request,
        name="dashboard/index.html",
        context={
            "usuario": usuario,
            "kpis": kpis,
            "productos_bajo_stock": productos_bajo_stock,
            "ultimo_cierre": ultimo_cierre,
            "datos_grafico": datos_grafico,
        },
    )


def _obtener_kpis(db: Session) -> DashboardKPIs:
    """Obtiene los KPIs del dashboard."""
    hoy = date.today()
    inicio_mes = date(hoy.year, hoy.month, 1)
    
    # Ventas del día
    ventas_hoy = db.scalar(
        select(func.sum(Factura.total_bs)).where(
            Factura.estado == "EMITIDA",
            func.date(Factura.fecha_emision) == hoy,
        )
    ) or Decimal("0.00")
    
    # Ventas del mes
    ventas_mes = db.scalar(
        select(func.sum(Factura.total_bs)).where(
            Factura.estado == "EMITIDA",
            func.date(Factura.fecha_emision) >= inicio_mes,
        )
    ) or Decimal("0.00")
    
    # CxC pendiente
    total_cxc = db.scalar(
        select(func.sum(CuentaPorCobrar.saldo_pendiente_bs)).where(
            CuentaPorCobrar.estado == "PENDIENTE",
        )
    ) or Decimal("0.00")
    
    # CxP pendiente
    total_cxp = db.scalar(
        select(func.sum(CuentaPorPagar.saldo_pendiente_bs)).where(
            CuentaPorPagar.saldo_pendiente_bs > 0,
        )
    ) or Decimal("0.00")
    
    # Productos bajo stock
    productos_bajo = db.scalar(
        select(func.count(Producto.id)).where(
            Producto.activo.is_(True),
            Producto.stock_actual <= Producto.stock_minimo,
        )
    ) or 0
    
    # Alertas detalladas
    alertas = db.scalars(
        select(Producto).where(
            Producto.activo.is_(True),
            Producto.stock_actual <= Producto.stock_minimo,
        )
    ).all()
    alertas_stock = [
        AlertaStock(
            producto_id=p.id,
            codigo_barras=p.codigo_barras,
            descripcion=p.descripcion,
            stock_actual=p.stock_actual,
            stock_minimo=p.stock_minimo,
            categoria=p.categoria.nombre if p.categoria else "Sin categoría",
        )
        for p in alertas
    ]
    
    return DashboardKPIs(
        ventas_hoy_bs=ventas_hoy,
        ventas_hoy_usd=ventas_hoy / Decimal("1.00"),  # Simplificado
        ventas_mes_bs=ventas_mes,
        ventas_mes_usd=ventas_mes / Decimal("1.00"),
        total_cxc_pendiente=total_cxc,
        total_cxp_pendiente=total_cxp,
        productos_bajo_stock=productos_bajo,
        alertas_stock=alertas_stock,
    )


def _datos_grafico_ventas(db: Session) -> dict:
    """Obtiene datos para gráfico de ventas de los últimos 30 días."""
    from datetime import timedelta
    
    fecha_desde = date.today() - timedelta(days=30)
    
    # Consulta de ventas por día
    stmt = (
        select(
            func.date(Factura.fecha_emision).label("fecha"),
            func.sum(Factura.total_bs).label("total_bs"),
            func.count(Factura.id).label("cantidad"),
        )
        .where(
            Factura.estado == "EMITIDA",
            func.date(Factura.fecha_emision) >= fecha_desde,
        )
        .group_by(func.date(Factura.fecha_emision))
        .order_by(func.date(Factura.fecha_emision))
    )
    
    resultados = db.execute(stmt).all()
    
    fechas_formateadas = []
    for r in resultados:
        if isinstance(r.fecha, str):
            try:
                dt = datetime.strptime(r.fecha, "%Y-%m-%d")
                fechas_formateadas.append(dt.strftime("%d/%m"))
            except ValueError:
                fechas_formateadas.append(r.fecha)
        elif hasattr(r.fecha, "strftime"):
            fechas_formateadas.append(r.fecha.strftime("%d/%m"))
        else:
            fechas_formateadas.append(str(r.fecha))

    return {
        "fechas": fechas_formateadas,
        "totales": [float(r.total_bs) for r in resultados],
        "cantidades": [r.cantidad for r in resultados],
    }


# ============================================================
# API - GRÁFICO DE VENTAS
# ============================================================

@router.get("/grafico-ventas", response_class=JSONResponse)
async def grafico_ventas(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Endpoint JSON para datos del gráfico de ventas."""
    datos = _datos_grafico_ventas(db)
    return datos


# ============================================================
# BITÁCORA DE AUDITORÍA
# ============================================================

@router.get("/auditoria", response_class=HTMLResponse)
async def auditoria_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permission("auditoria", "ver")),
):
    """Vista de bitácora de auditoría."""
    return templates.TemplateResponse(
        request=request,
        name="dashboard/bitacora.html",
        context={"usuario": usuario},
    )


@router.get("/auditoria/data", response_class=JSONResponse)
async def auditoria_data(
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(require_permission("auditoria", "ver")),
    usuario: Optional[str] = Query(default=None),
    modulo: Optional[str] = Query(default=None),
    accion: Optional[str] = Query(default=None),
    fecha_desde: Optional[date] = Query(default=None),
    fecha_hasta: Optional[date] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """
    Consulta de bitácora con filtros y paginación.
    """
    stmt = select(BitacoraAuditoria).join(Usuario, BitacoraAuditoria.usuario_id == Usuario.id, isouter=True)
    
    # Filtros
    if usuario:
        stmt = stmt.where(Usuario.username.contains(usuario) | Usuario.nombre_completo.contains(usuario))
    if modulo:
        stmt = stmt.where(BitacoraAuditoria.modulo == modulo)
    if accion:
        stmt = stmt.where(BitacoraAuditoria.accion == accion)
    if fecha_desde:
        stmt = stmt.where(func.date(BitacoraAuditoria.fecha) >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(func.date(BitacoraAuditoria.fecha) <= fecha_hasta)
        
    # Conteo total para paginación
    total_registros = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    total_paginas = (total_registros + page_size - 1) // page_size if total_registros > 0 else 0

    # Ordenar y paginar
    stmt = stmt.order_by(BitacoraAuditoria.fecha.desc()).offset((page - 1) * page_size).limit(page_size)
    resultados = db.execute(stmt).scalars().all()

    items = [
        BitacoraItem(
            id=item.id,
            fecha=item.fecha,
            usuario_nombre=item.usuario.username if item.usuario else "Sistema",
            modulo=item.modulo,
            accion=item.accion,
            descripcion=item.detalles or "",
            ip_address=item.ip_address,
        )
        for item in resultados
    ]

    return BitacoraResumen(
        total_registros=total_registros,
        pagina=page,
        page_size=page_size,
        total_paginas=total_paginas,
        items=items,
    ).model_dump()


# ============================================================
# REPORTES GERENCIALES
# ============================================================

@router.get("/reportes/mas-vendidos", response_class=JSONResponse)
async def reporte_mas_vendidos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permission("reportes", "ver")),
    limite: int = Query(default=10, ge=1, le=100),
):
    """Top productos más vendidos por cantidad e ingresos."""
    tasa = db.scalar(select(TasaRef).order_by(TasaRef.fecha.desc()).limit(1))
    tasa_val = tasa.monto_bs if tasa else Decimal("1.00")

    stmt = (
        select(
            Producto,
            func.sum(DetalleVenta.cantidad).label("total_cantidad"),
            func.sum(DetalleVenta.total_linea_bs).label("total_ingresos_bs"),
        )
        .join(DetalleVenta, Producto.id == DetalleVenta.producto_id)
        .group_by(Producto.id)
        .order_by(func.sum(DetalleVenta.cantidad).desc())
        .limit(limite)
    )

    resultados = db.execute(stmt).all()

    items = []
    for prod, cant, ingresos_bs in resultados:
        ingresos_usd = ingresos_bs / tasa_val if ingresos_bs else Decimal("0.00")
        items.append({
            "producto": prod.descripcion,
            "categoria": prod.categoria.nombre if prod.categoria else "General",
            "cantidad": float(cant or 0),
            "total_bs": float(ingresos_bs or 0),
            "total_usd": float(ingresos_usd),
        })

    return items


@router.get("/reportes/rentabilidad", response_class=JSONResponse)
async def reporte_rentabilidad(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permission("reportes", "ver")),
):
    """Reporte de rentabilidad por producto."""
    tasa = db.scalar(select(TasaRef).order_by(TasaRef.fecha.desc()).limit(1))
    tasa_val = tasa.monto_bs if tasa else Decimal("1.00")

    stmt = select(Producto)
    productos = db.execute(stmt).scalars().all()

    items = []
    for p in productos:
        # Precio de venta en Bs
        precio_venta_bs = p.precio_ref * tasa_val
        
        # Obtener último costo de compra en Bs si existe
        ultimo_costo = db.scalar(
            select(DetalleCompra.costo_unitario_bs)
            .where(DetalleCompra.producto_id == p.id)
            .order_by(DetalleCompra.id.desc())
            .limit(1)
        )
        
        # Si no hay costo de compra, asumir costo de 70% del precio de venta (30% de ganancia)
        costo_bs = ultimo_costo if ultimo_costo is not None else (precio_venta_bs * Decimal("0.70"))
        
        margen_bs = precio_venta_bs - costo_bs
        margen_porcentaje = (margen_bs / precio_venta_bs * 100) if precio_venta_bs > 0 else Decimal("0.00")

        items.append({
            "producto": p.descripcion,
            "costo": float(costo_bs),
            "precio": float(precio_venta_bs),
            "margen_bs": float(margen_bs),
            "margen_%": float(margen_porcentaje),
        })

    return items


@router.get("/reportes/ventas-periodo", response_class=JSONResponse)
async def reporte_ventas_periodo(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permission("reportes", "ver")),
    fecha_desde: Optional[date] = Query(default=None),
    fecha_hasta: Optional[date] = Query(default=None),
):
    """Ventas agrupadas por fecha, categoría y método de pago."""
    tasa = db.scalar(select(TasaRef).order_by(TasaRef.fecha.desc()).limit(1))
    tasa_val = tasa.monto_bs if tasa else Decimal("1.00")

    stmt = (
        select(
            func.date(Factura.fecha_emision).label("fecha"),
            Categoria.nombre.label("categoria"),
            PagoVenta.moneda.label("metodo_pago"),
            func.count(Factura.id).label("cantidad"),
            func.sum(DetalleVenta.total_linea_bs).label("total_bs"),
        )
        .join(DetalleVenta, Factura.id == DetalleVenta.factura_id)
        .join(Producto, DetalleVenta.producto_id == Producto.id)
        .join(Categoria, Producto.categoria_id == Categoria.id)
        .join(PagoVenta, Factura.id == PagoVenta.factura_id, isouter=True)
        .where(Factura.estado == "EMITIDA")
    )

    if fecha_desde:
        stmt = stmt.where(func.date(Factura.fecha_emision) >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(func.date(Factura.fecha_emision) <= fecha_hasta)

    stmt = stmt.group_by(
        func.date(Factura.fecha_emision),
        Categoria.nombre,
        PagoVenta.moneda
    ).order_by(func.date(Factura.fecha_emision).desc())

    resultados = db.execute(stmt).all()

    items = []
    for fecha, cat, pago, cant, total_bs in resultados:
        total_usd = total_bs / tasa_val if total_bs else Decimal("0.00")
        items.append({
            "fecha": fecha.strftime("%Y-%m-%d") if isinstance(fecha, (date, datetime)) else str(fecha),
            "categoria": cat,
            "metodo_pago": pago or "Por registrar",
            "cantidad": cant,
            "total_bs": float(total_bs or 0),
            "total_usd": float(total_usd),
        })

    return items

"""
Router de Ventas y POS — Facturación, Cobros y Kardex.

Rutas:
- GET  /pos                    : Vista principal del POS.
- GET  /pos/buscar-producto    : Búsqueda rápida de productos (JSON/HTMX).
- GET  /pos/buscar-cliente     : Búsqueda rápida de clientes (JSON/HTMX).
- POST /pos/procesar-venta     : Procesa una venta completa (transacción atómica).
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.database import get_db
from app.models.inventory import KardexMovimiento, Producto
from app.models.sales import (
    Cliente,
    CorrelativoFiscal,
    CuentaPorCobrar,
    DetalleVenta,
    Factura,
    FormaPago,
    PagoVenta,
    TasaRef,
)
from app.schemas.sales import VentaCreate, VentaItemCreate, VentaPagoCreate

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ============================================================
# VISTAS
# ============================================================

@router.get("/pos", response_class=HTMLResponse)
async def pos_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "ver")),
):
    """Vista principal del POS/Terminal de Ventas."""
    tasa = db.scalar(
        select(TasaRef).order_by(TasaRef.fecha.desc()).limit(1)
    )

    return templates.TemplateResponse(
        request=request,
        name="sales/pos.html",
        context={"usuario": usuario, "tasa": tasa},
    )


# ============================================================
# BÚSQUEDAS (JSON/HTMX)
# ============================================================

@router.get("/pos/buscar-producto", response_class=JSONResponse)
async def buscar_producto(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "ver")),
    q: str = Query(default="", description="Texto de búsqueda"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Busca productos por código de barras, SKU o descripción.
    Devuelve resultados ligeros para autocompletado.
    """
    if not q.strip():
        return {"productos": []}

    like = f"%{q.strip()}%"
    stmt = (
        select(Producto)
        .where(
            Producto.activo.is_(True),
            or_(
                Producto.codigo_barras.ilike(like),
                Producto.descripcion.ilike(like),
            ),
        )
        .order_by(Producto.codigo_barras)
        .limit(limit)
    )

    productos = db.execute(stmt).scalars().all()
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


@router.get("/pos/buscar-cliente", response_class=JSONResponse)
async def buscar_cliente(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "ver")),
    q: str = Query(default="", description="RIF/Cédula o nombre"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Busca clientes por RIF/Cédula o razón social."""
    if not q.strip():
        return {"clientes": []}

    like = f"%{q.strip()}%"
    stmt = (
        select(Cliente)
        .where(
            or_(
                Cliente.cedula_rif.ilike(like),
                Cliente.razon_social.ilike(like),
            )
        )
        .order_by(Cliente.razon_social)
        .limit(limit)
    )

    clientes = db.execute(stmt).scalars().all()
    return {
        "clientes": [
            {
                "id": c.id,
                "cedula_rif": c.cedula_rif,
                "razon_social": c.razon_social,
            }
            for c in clientes
        ]
    }


# ============================================================
# PROCESAR VENTA (Transacción Atómica)
# ============================================================

@router.post("/pos/procesar-venta", response_class=JSONResponse)
async def procesar_venta(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "crear")),
):
    """
    Procesa una venta completa dentro de una transacción atómica.

    Pasos:
    1. Valida stock disponible.
    2. Asigna correlativo fiscal.
    3. Crea factura y detalle_ventas.
    4. Actualiza stock y genera movimientos Kardex (SALIDA).
    5. Registra pagos.
    6. Si hay saldo pendiente, genera Cuenta por Cobrar.
    """
    try:
        data = await request.json()
        venta = VentaCreate(**data)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Datos inválidos: {e}"})

    # Obtener tasa del día
    tasa_ref = db.scalar(select(TasaRef).order_by(TasaRef.fecha.desc()).limit(1))
    if not tasa_ref:
        return JSONResponse(status_code=400, content={"error": "No hay tasa de cambio registrada."})

    # Iniciar transacción atómica
    with db.begin():
        # 1. Validar stock y preparar cálculos
        productos_validados = []
        subtotal_bs = Decimal("0.00")
        iva_bs = Decimal("0.00")

        for item in venta.items:
            prod = db.get(Producto, item.producto_id)
            if not prod or not prod.activo:
                return JSONResponse(
                    status_code=400,
                    content={"error": f"Producto {item.producto_id} no válido."},
                )

            if prod.stock_actual < item.cantidad:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": f"Stock insuficiente para {prod.descripcion}. "
                        f"Disponible: {prod.stock_actual}, solicitado: {item.cantidad}"
                    },
                )

            # Calcular con redondeo explícito a 2 decimales
            precio_unitario_bs = Decimal(f"{float(item.precio_unitario_usd * tasa_ref.monto_bs):.2f}")
            total_linea_bs = Decimal(f"{float(precio_unitario_bs * item.cantidad):.2f}")
            subtotal_bs += total_linea_bs
            iva_linea = Decimal(f"{float(total_linea_bs * (item.tasa_iva / Decimal('100'))):.2f}")
            iva_bs += iva_linea

            productos_validados.append(
                {
                    "producto": prod,
                    "cantidad": item.cantidad,
                    "precio_unitario_bs": precio_unitario_bs,
                    "tasa_iva": item.tasa_iva,
                    "total_linea_bs": total_linea_bs,
                }
            )

        # total_bs debe ser exactamente la suma para pasar CHECKs
        total_bs = subtotal_bs + iva_bs
        total_ref = total_bs / tasa_ref.monto_bs

        # 2. Asignar correlativo fiscal
        correlativo = db.scalar(
            select(CorrelativoFiscal).where(
                CorrelativoFiscal.tipo_documento == "FACTURA",
                CorrelativoFiscal.serie == "A",
            )
        )
        if not correlativo:
            correlativo = CorrelativoFiscal(
                tipo_documento="FACTURA", serie="A", ultimo_numero=0
            )
            db.add(correlativo)
            db.flush()

        numero_factura = f"FA-A-{correlativo.ultimo_numero + 1:06d}"
        correlativo.ultimo_numero += 1

        # 3. Crear factura
        factura = Factura(
            numero_factura=numero_factura,
            correlativo=correlativo.ultimo_numero,
            cliente_id=venta.cliente_id or 1,  # Cliente contado por defecto
            usuario_id=usuario.id,
            tasa_ref_monto=tasa_ref.monto_bs,
            subtotal_bs=subtotal_bs,
            iva_bs=iva_bs,
            igtf_bs=Decimal("0.00"),
            total_bs=total_bs,
            total_ref=total_ref,
            estado="EMITIDA",
            fecha_emision=datetime.now(timezone.utc),
        )
        db.add(factura)
        db.flush()

        # 4. Detalle de ventas y actualización de stock/kardex
        for pv in productos_validados:
            detalle = DetalleVenta(
                factura_id=factura.id,
                producto_id=pv["producto"].id,
                cantidad=pv["cantidad"],
                precio_unitario_bs=pv["precio_unitario_bs"],
                alicuota_porcentaje=pv["tasa_iva"],
                total_linea_bs=pv["total_linea_bs"],
            )
            db.add(detalle)

            # Actualizar stock
            pv["producto"].stock_actual -= pv["cantidad"]

            # Movimiento Kardex SALIDA
            kardex = KardexMovimiento(
                producto_id=pv["producto"].id,
                tipo_movimiento="SALIDA",
                cantidad=pv["cantidad"],
                costo_ref=pv["precio_unitario_bs"],
                origen_id=factura.id,
                fecha=datetime.now(timezone.utc),
            )
            db.add(kardex)

        # 5. Registrar pagos
        total_pagado_bs = Decimal("0.00")
        for pago in venta.pagos:
            monto_bs = pago.monto_ves if pago.monto_ves else pago.monto_usd * tasa_ref.monto_bs
            total_pagado_bs += monto_bs

            pago_venta = PagoVenta(
                factura_id=factura.id,
                forma_pago_id=pago.forma_pago_id,
                monto_origen=pago.monto_usd,
                moneda="USD",
                tasa_cambio=tasa_ref.monto_bs,
                monto_bs=monto_bs,
                referencia=pago.referencia,
            )
            db.add(pago_venta)

        # 6. Cuentas por Cobrar si hay saldo pendiente
        saldo_pendiente = total_bs - total_pagado_bs
        if saldo_pendiente > 0:
            cxc = CuentaPorCobrar(
                factura_id=factura.id,
                cliente_id=venta.cliente_id or 1,
                monto_total_bs=total_bs,
                saldo_pendiente_bs=saldo_pendiente,
                estado="PENDIENTE",
                fecha_vencimiento=date.today(),
            )
            db.add(cxc)

        # Commit automático al salir del bloque with

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "factura_id": factura.id,
            "numero_factura": numero_factura,
            "total_bs": float(total_bs),
            "total_ref": float(total_ref),
        },
    )
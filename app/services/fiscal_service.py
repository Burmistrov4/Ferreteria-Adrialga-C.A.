"""
Servicios de negocio — Flujo fiscal de caja, Reporte X y Cierre Z.

Contiene lógica de:
- apertura de caja
- verificación de sesión abierta
- cálculo de Reporte X
- generación de Cierre Z fiscal con cierre de sesión
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Factura, FormaPago, PagoVenta, TasaRef
from app.models.cash import CierreCaja, SesionCaja
from app.models.sales import TasaRef as TasaRefModel


def get_active_caja(db: Session, usuario_id: int) -> Optional[SesionCaja]:
    """Retorna la sesión de caja abierta del usuario si existe."""
    return db.scalar(
        select(SesionCaja).where(
            SesionCaja.usuario_id == usuario_id,
            SesionCaja.estado == "ABIERTA",
        )
    )


def get_next_reporte_z_number(db: Session) -> int:
    """Genera el siguiente número correlativo de Reporte Z."""
    mayor = db.scalar(select(func.max(CierreCaja.numero_reporte_z)))
    if mayor is None:
        return 1
    return int(mayor) + 1


def open_caja(
    db: Session,
    usuario_id: int,
    monto_inicial_bs: Decimal,
    monto_inicial_usd: Decimal,
    tasa_ref_monto: Decimal,
) -> SesionCaja:
    """Abre una nueva sesión de caja para el usuario."""
    if get_active_caja(db, usuario_id):
        raise ValueError("Ya existe una sesión de caja abierta para este usuario.")

    caja = SesionCaja(
        usuario_id=usuario_id,
        monto_inicial_bs=monto_inicial_bs,
        monto_inicial_usd=monto_inicial_usd,
        tasa_ref_monto=tasa_ref_monto,
        estado="ABIERTA",
    )
    db.add(caja)
    db.flush()
    return caja


def calculate_reporte_x(db: Session, sesion_id: int) -> Dict[str, Decimal]:
    """Calcula los totales del Reporte X para la sesión activa."""
    facturas = db.execute(
        select(Factura).where(
            Factura.sesion_caja_id == sesion_id,
            Factura.estado == "EMITIDA",
        )
    ).scalars().all()

    total_ventas_bs = Decimal("0.00")
    total_ventas_usd = Decimal("0.00")
    total_iva_bs = Decimal("0.00")
    total_igtf_bs = Decimal("0.00")
    for factura in facturas:
        total_ventas_bs += factura.total_bs
        total_ventas_usd += factura.total_ref
        total_iva_bs += factura.iva_bs
        total_igtf_bs += factura.igtf_bs

    total_efectivo_bs = Decimal("0.00")
    total_efectivo_usd = Decimal("0.00")
    total_pago_movil = Decimal("0.00")
    total_punto_de_venta = Decimal("0.00")
    total_transferencia = Decimal("0.00")

    if facturas:
        factura_ids = [factura.id for factura in facturas]
        pagos = db.execute(
            select(PagoVenta, FormaPago).join(FormaPago).where(
                PagoVenta.factura_id.in_(factura_ids)
            )
        ).all()

        for pago, forma in pagos:
            codigo = forma.codigo.upper()
            if codigo in ("EFECTIVO_USD",):
                total_efectivo_usd += pago.monto_origen
            elif codigo in ("EFECTIVO_VES",):
                total_efectivo_bs += pago.monto_bs
            elif codigo in ("PAGO_MOVIL", "PAGO MOVIL", "PAGOMOVIL"):
                total_pago_movil += pago.monto_bs
            elif codigo in ("PUNTO_VENTA", "PUNTO DE VENTA", "PUNTO_VENTA"):
                total_punto_de_venta += pago.monto_bs
            elif codigo in ("TRANSFERENCIA",):
                total_transferencia += pago.monto_bs
            else:
                total_efectivo_bs += pago.monto_bs

    return {
        "total_ventas_bs": total_ventas_bs,
        "total_ventas_usd": total_ventas_usd,
        "total_iva_bs": total_iva_bs,
        "total_igtf_bs": total_igtf_bs,
        "total_efectivo_bs": total_efectivo_bs,
        "total_efectivo_usd": total_efectivo_usd,
        "total_pago_movil": total_pago_movil,
        "total_punto_de_venta": total_punto_de_venta,
        "total_transferencia": total_transferencia,
    }


def close_caja(
    db: Session,
    sesion_id: int,
    efectivo_bs: Decimal,
    efectivo_usd: Decimal,
    pago_movil: Decimal,
    punto_venta: Decimal,
    transferencia: Decimal,
) -> CierreCaja:
    """Cierra la sesión de caja y genera el reporte Z de cierre fiscal."""
    sesion = db.get(SesionCaja, sesion_id)
    if not sesion or sesion.estado != "ABIERTA":
        raise ValueError("No existe una sesión de caja activa para cierre.")

    totales = calculate_reporte_x(db, sesion_id)

    total_ventas_bs = totales["total_ventas_bs"]
    total_ventas_usd = totales["total_ventas_usd"]
    total_iva_bs = totales["total_iva_bs"]
    total_igtf_bs = totales["total_igtf_bs"]

    total_declarado_bs = (
        efectivo_bs
        + pago_movil
        + punto_venta
        + transferencia
        + (efectivo_usd * sesion.tasa_ref_monto)
    )

    diferencia = total_declarado_bs - total_ventas_bs

    facturas = db.execute(
        select(Factura).where(
            Factura.sesion_caja_id == sesion_id,
            Factura.estado == "EMITIDA",
        )
    ).scalars().all()

    if not facturas:
        raise ValueError("No hay facturas emitidas en la sesión activa.")

    reporte_z = CierreCaja(
        sesion_caja_id=sesion.id,
        usuario_id=sesion.usuario_id,
        numero_reporte_z=get_next_reporte_z_number(db),
        total_ventas_bs=total_ventas_bs.quantize(Decimal("0.00")),
        total_ventas_usd=total_ventas_usd.quantize(Decimal("0.00")),
        total_iva_bs=total_iva_bs.quantize(Decimal("0.00")),
        total_igtf_bs=total_igtf_bs.quantize(Decimal("0.00")),
        total_efectivo_bs=efectivo_bs.quantize(Decimal("0.00")),
        total_efectivo_usd=efectivo_usd.quantize(Decimal("0.00")),
        total_pago_movil=pago_movil.quantize(Decimal("0.00")),
        total_punto_de_venta=punto_venta.quantize(Decimal("0.00")),
        total_transferencia=transferencia.quantize(Decimal("0.00")),
        diferencia_sobrante_faltante=diferencia.quantize(Decimal("0.00")),
        factura_inicio=facturas[0].numero_factura,
        factura_fin=facturas[-1].numero_factura,
        cantidad_operaciones=len(facturas),
    )
    db.add(reporte_z)

    sesion.estado = "CERRADA"
    sesion.fecha_cierre = datetime.now(timezone.utc)

    db.flush()
    return reporte_z


def get_current_tasa_ref(db: Session) -> TasaRefModel:
    """Retorna la tasa REF vigente o lanza error si no existe."""
    tasa_ref = db.scalar(select(TasaRefModel).order_by(TasaRefModel.fecha.desc()).limit(1))
    if not tasa_ref:
        raise ValueError("No hay tasa REF registrada.")
    return tasa_ref
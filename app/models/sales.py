"""
Modelos ORM — Módulo de Ventas, POS y Multimoneda.

Tablas: clientes, tasas_ref, correlativos_fiscales, facturas,
        detalle_ventas, formas_pago, pagos_venta, cuentas_por_cobrar
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Cliente(Base):
    """Tabla: clientes"""

    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cedula_rif: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    razon_social: Mapped[str] = mapped_column(String(150), nullable=False)
    direccion: Mapped[Optional[str]] = mapped_column(Text)
    telefono: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(120))
    limite_credito: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relaciones
    facturas: Mapped[List["Factura"]] = relationship(back_populates="cliente")
    cuentas_por_cobrar: Mapped[List["CuentaPorCobrar"]] = relationship(
        back_populates="cliente"
    )


class TasaRef(Base):
    """Tabla: tasas_ref — Tasa REF / BCV diaria"""

    __tablename__ = "tasas_ref"
    __table_args__ = (
        CheckConstraint("monto_bs > 0", name="chk_tasa_monto_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fecha: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    monto_bs: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    origen: Mapped[str] = mapped_column(String(30), default="BCV", nullable=False)

    # Relaciones
    facturas: Mapped[List["Factura"]] = relationship(back_populates="tasa_ref")


class CorrelativoFiscal(Base):
    """Tabla: correlativos_fiscales"""

    __tablename__ = "correlativos_fiscales"
    __table_args__ = (
        UniqueConstraint("tipo_documento", "serie", name="uq_correlativo_tipo_serie"),
        CheckConstraint("ultimo_numero >= 0", name="chk_ultimo_numero_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tipo_documento: Mapped[str] = mapped_column(String(20), nullable=False)
    serie: Mapped[str] = mapped_column(String(10), nullable=False)
    ultimo_numero: Mapped[int] = mapped_column(default=0, nullable=False)


class Factura(Base):
    """Tabla: facturas"""

    __tablename__ = "facturas"
    __table_args__ = (
        CheckConstraint("subtotal_bs >= 0", name="chk_factura_subtotal_positivo"),
        CheckConstraint("iva_bs >= 0", name="chk_factura_iva_positivo"),
        CheckConstraint("igtf_bs >= 0", name="chk_factura_igtf_positivo"),
        CheckConstraint("total_bs >= 0", name="chk_factura_total_positivo"),
        CheckConstraint("total_ref >= 0", name="chk_factura_total_ref_positivo"),
        CheckConstraint(
            "estado IN ('BORRADOR', 'EMITIDA', 'ANULADA', 'PENDIENTE_CONFIRMACION')",
            name="chk_factura_estado",
        ),
        # Nota: El CHECK total_bs = subtotal_bs + iva_bs + igtf_bs se mantiene en PostgreSQL
        # pero se omite en SQLite por compatibilidad de redondeo.
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero_factura: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    correlativo: Mapped[int] = mapped_column(nullable=False)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    tasa_ref_id: Mapped[int] = mapped_column(
        ForeignKey("tasas_ref.id"), nullable=False
    )
    sesion_caja_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sesiones_caja.id"), nullable=True
    )
    subtotal_bs: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
    iva_bs: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    igtf_bs: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_bs: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_ref: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    estado: Mapped[str] = mapped_column(String(20), default="EMITIDA", nullable=False)
    fecha_emision: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relaciones
    cliente: Mapped["Cliente"] = relationship(back_populates="facturas")
    usuario: Mapped["Usuario"] = relationship(back_populates="facturas")
    tasa_ref: Mapped["TasaRef"] = relationship(back_populates="facturas")
    detalles: Mapped[List["DetalleVenta"]] = relationship(
        back_populates="factura", cascade="all, delete-orphan"
    )
    pagos: Mapped[List["PagoVenta"]] = relationship(
        back_populates="factura", cascade="all, delete-orphan"
    )
    cuentas_por_cobrar: Mapped[List["CuentaPorCobrar"]] = relationship(
        back_populates="factura"
    )
    sesion_caja: Mapped[Optional["SesionCaja"]] = relationship(back_populates="facturas")
    detalle_declaraciones: Mapped[List["DetalleDeclaracionIVA"]] = relationship(
        back_populates="factura"
    )


class DetalleVenta(Base):
    """Tabla: detalle_ventas"""

    __tablename__ = "detalle_ventas"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="chk_detalle_venta_cantidad_positiva"),
        CheckConstraint(
            "precio_unitario_bs >= 0", name="chk_detalle_venta_precio_positivo"
        ),
        CheckConstraint(
            "alicuota_porcentaje IN (0, 8, 16, 31)",
            name="chk_detalle_venta_alicuota",
        ),
        CheckConstraint(
            "total_linea_bs >= 0", name="chk_detalle_venta_total_positivo"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    factura_id: Mapped[int] = mapped_column(
        ForeignKey("facturas.id"), nullable=False
    )
    producto_id: Mapped[int] = mapped_column(
        ForeignKey("productos.id"), nullable=False
    )
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    precio_unitario_bs: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    alicuota_porcentaje: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    total_linea_bs: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Relaciones
    factura: Mapped["Factura"] = relationship(back_populates="detalles")
    producto: Mapped["Producto"] = relationship(back_populates="detalle_ventas")


class FormaPago(Base):
    """Tabla: formas_pago"""

    __tablename__ = "formas_pago"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    requiere_referencia: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relaciones
    pagos: Mapped[List["PagoVenta"]] = relationship(back_populates="forma_pago")


class PagoVenta(Base):
    """Tabla: pagos_venta"""

    __tablename__ = "pagos_venta"
    __table_args__ = (
        CheckConstraint("monto_origen >= 0", name="chk_pago_monto_origen_positivo"),
        CheckConstraint("moneda IN ('BS', 'USD')", name="chk_pago_moneda"),
        CheckConstraint("tasa_cambio > 0", name="chk_pago_tasa_cambio_positiva"),
        CheckConstraint("monto_bs >= 0", name="chk_pago_monto_bs_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    factura_id: Mapped[int] = mapped_column(
        ForeignKey("facturas.id"), nullable=False
    )
    forma_pago_id: Mapped[int] = mapped_column(
        ForeignKey("formas_pago.id"), nullable=False
    )
    monto_origen: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), default="BS", nullable=False)
    tasa_cambio: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), default=Decimal("1.0000"), nullable=False
    )
    monto_bs: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    referencia: Mapped[Optional[str]] = mapped_column(String(50))

    # Relaciones
    factura: Mapped["Factura"] = relationship(back_populates="pagos")
    forma_pago: Mapped["FormaPago"] = relationship(back_populates="pagos")


class CuentaPorCobrar(Base):
    """Tabla: cuentas_por_cobrar"""

    __tablename__ = "cuentas_por_cobrar"
    __table_args__ = (
        CheckConstraint("monto_total_bs > 0", name="chk_cxc_monto_total_positivo"),
        CheckConstraint(
            "saldo_pendiente_bs >= 0", name="chk_cxc_saldo_pendiente_positivo"
        ),
        CheckConstraint(
            "estado IN ('PENDIENTE', 'SALDADA', 'VENCIDA')", name="chk_cxc_estado"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    factura_id: Mapped[int] = mapped_column(
        ForeignKey("facturas.id"), nullable=False
    )
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    monto_total_bs: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    saldo_pendiente_bs: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE", nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)

    # Relaciones
    factura: Mapped["Factura"] = relationship(back_populates="cuentas_por_cobrar")
    cliente: Mapped["Cliente"] = relationship(back_populates="cuentas_por_cobrar")
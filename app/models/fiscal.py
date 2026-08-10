"""
Modelos ORM — Módulo Fiscal SENIAT y Cierres.

Tablas: cierres_z, declaracion_iva, detalle_declaracion_iva
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class CierreZ(Base):
    """Tabla: cierres_z"""

    __tablename__ = "cierres_z"
    __table_args__ = (
        CheckConstraint("total_ventas_bs >= 0", name="chk_cierre_total_ventas_positivo"),
        CheckConstraint("total_iva_bs >= 0", name="chk_cierre_total_iva_positivo"),
        CheckConstraint("total_igtf_bs >= 0", name="chk_cierre_total_igtf_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    fecha: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    total_ventas_bs: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
    total_iva_bs: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
    total_igtf_bs: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
    factura_inicio: Mapped[str] = mapped_column(String(30), nullable=False)
    factura_fin: Mapped[str] = mapped_column(String(30), nullable=False)

    # Relaciones
    usuario: Mapped["Usuario"] = relationship(back_populates="cierres_z")


class RetencionIVA(Base):
    """Tabla: retenciones_iva"""

    __tablename__ = "retenciones_iva"
    __table_args__ = (
        CheckConstraint("porcentaje_retencion IN (75, 100)", name="chk_retencion_iva_porcentaje"),
        CheckConstraint("monto_retenido >= 0", name="chk_retencion_iva_monto_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras.id"), nullable=False)
    numero_comprobante: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    fecha_retencion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    base_imponible: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    porcentaje_retencion: Mapped[int] = mapped_column(nullable=False)
    monto_retenido: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Relaciones
    compra: Mapped["Compra"] = relationship(back_populates="retencion_iva")


class RetencionISLR(Base):
    """Tabla: retenciones_islr"""

    __tablename__ = "retenciones_islr"
    __table_args__ = (
        CheckConstraint("porcentaje_retencion > 0", name="chk_retencion_islr_porcentaje_positivo"),
        CheckConstraint("monto_retenido >= 0", name="chk_retencion_islr_monto_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras.id"), nullable=False)
    numero_comprobante: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    fecha_retencion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    concepto: Mapped[str] = mapped_column(String(100), nullable=False)
    base_imponible: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    porcentaje_retencion: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    sustraendo: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    monto_retenido: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Relaciones
    compra: Mapped["Compra"] = relationship(back_populates="retencion_islr")


class DeclaracionIVA(Base):
    """Tabla: declaracion_iva"""

    __tablename__ = "declaracion_iva"
    __table_args__ = (
        UniqueConstraint("periodo_mes", "periodo_anio", name="uq_declaracion_periodo"),
        CheckConstraint(
            "periodo_mes BETWEEN 1 AND 12", name="chk_declaracion_mes_valido"
        ),
        CheckConstraint("periodo_anio >= 2000", name="chk_declaracion_anio_valido"),
        CheckConstraint(
            "total_debito_fiscal >= 0", name="chk_declaracion_debito_positivo"
        ),
        CheckConstraint(
            "total_credito_fiscal >= 0", name="chk_declaracion_credito_positivo"
        ),
        CheckConstraint(
            "estatus IN ('BORRADOR', 'DECLARADA', 'PROCESADA')",
            name="chk_declaracion_estatus",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    periodo_mes: Mapped[int] = mapped_column(nullable=False)
    periodo_anio: Mapped[int] = mapped_column(nullable=False)
    total_debito_fiscal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
    total_credito_fiscal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
    estatus: Mapped[str] = mapped_column(String(20), default="BORRADOR", nullable=False)

    # Relaciones
    detalles: Mapped[List["DetalleDeclaracionIVA"]] = relationship(
        back_populates="declaracion", cascade="all, delete-orphan"
    )


class DetalleDeclaracionIVA(Base):
    """Tabla: detalle_declaracion_iva"""

    __tablename__ = "detalle_declaracion_iva"
    __table_args__ = (
        CheckConstraint(
            "tipo_transaccion IN ('VENTA', 'COMPRA')",
            name="chk_detalle_declaracion_tipo",
        ),
        CheckConstraint(
            "base_imponible >= 0", name="chk_detalle_declaracion_base_positiva"
        ),
        CheckConstraint(
            "monto_iva >= 0", name="chk_detalle_declaracion_iva_positivo"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    declaracion_id: Mapped[int] = mapped_column(
        ForeignKey("declaracion_iva.id"), nullable=False
    )
    tipo_transaccion: Mapped[str] = mapped_column(String(10), nullable=False)
    factura_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("facturas.id"), nullable=True
    )
    compra_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("compras.id"), nullable=True
    )
    base_imponible: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
    monto_iva: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )

    # Relaciones
    declaracion: Mapped["DeclaracionIVA"] = relationship(back_populates="detalles")
    factura: Mapped[Optional["Factura"]] = relationship(
        back_populates="detalle_declaraciones"
    )
    compra: Mapped[Optional["Compra"]] = relationship(
        back_populates="detalle_declaraciones"
    )
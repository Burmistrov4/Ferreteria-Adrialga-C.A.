"""
Modelos ORM — Módulo de Caja y Cierres de Caja.

Tablas:
- sesiones_caja
- cierres_caja
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class SesionCaja(Base):
    """Tabla: sesiones_caja"""

    __tablename__ = "sesiones_caja"
    __table_args__ = (
        CheckConstraint(
            "monto_inicial_bs >= 0", name="chk_sesion_caja_monto_inicial_bs"
        ),
        CheckConstraint(
            "monto_inicial_usd >= 0", name="chk_sesion_caja_monto_inicial_usd"
        ),
        CheckConstraint(
            "tasa_ref_monto > 0", name="chk_sesion_caja_tasa_ref_positiva"
        ),
        CheckConstraint(
            "estado IN ('ABIERTA', 'CERRADA')", name="chk_sesion_caja_estado"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    fecha_apertura: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    fecha_cierre: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    monto_inicial_bs: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    monto_inicial_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    tasa_ref_monto: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="ABIERTA", nullable=False)

    # Relaciones
    usuario = relationship("Usuario", back_populates="sesiones_caja")
    facturas: Mapped[List["Factura"]] = relationship(
        back_populates="sesion_caja", cascade="all, delete-orphan"
    )
    cierres: Mapped[List["CierreCaja"]] = relationship(
        back_populates="sesion_caja", cascade="all, delete-orphan"
    )


class CierreCaja(Base):
    """Tabla: cierres_caja"""

    __tablename__ = "cierres_caja"
    __table_args__ = (
        UniqueConstraint("numero_reporte_z", name="uq_cierre_caja_numero_reporte_z"),
        CheckConstraint("total_ventas_bs >= 0", name="chk_cierre_caja_total_ventas_bs"),
        CheckConstraint("total_ventas_usd >= 0", name="chk_cierre_caja_total_ventas_usd"),
        CheckConstraint("total_iva_bs >= 0", name="chk_cierre_caja_total_iva_bs"),
        CheckConstraint("total_igtf_bs >= 0", name="chk_cierre_caja_total_igtf_bs"),
        CheckConstraint("total_efectivo_bs >= 0", name="chk_cierre_caja_total_efectivo_bs"),
        CheckConstraint("total_efectivo_usd >= 0", name="chk_cierre_caja_total_efectivo_usd"),
        CheckConstraint("total_pago_movil >= 0", name="chk_cierre_caja_total_pago_movil"),
        CheckConstraint("total_punto_de_venta >= 0", name="chk_cierre_caja_total_punto_de_venta"),
        CheckConstraint("total_transferencia >= 0", name="chk_cierre_caja_total_transferencia"),
        CheckConstraint(
            "diferencia_sobrante_faltante IS NOT NULL",
            name="chk_cierre_caja_diferencia_no_nula",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sesion_caja_id: Mapped[int] = mapped_column(ForeignKey("sesiones_caja.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    numero_reporte_z: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    total_ventas_bs: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_ventas_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_iva_bs: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_igtf_bs: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_efectivo_bs: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_efectivo_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_pago_movil: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_punto_de_venta: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_transferencia: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    diferencia_sobrante_faltante: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00")
    )
    factura_inicio: Mapped[str] = mapped_column(String(30), nullable=False)
    factura_fin: Mapped[str] = mapped_column(String(30), nullable=False)
    cantidad_operaciones: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relaciones
    sesion_caja = relationship("SesionCaja", back_populates="cierres")
    usuario = relationship("Usuario")
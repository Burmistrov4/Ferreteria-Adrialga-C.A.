"""
Modelos ORM — Módulo de Compras y Proveedores.

Tablas: proveedores, compras, detalle_compras, cuentas_por_pagar
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Proveedor(Base):
    """Tabla: proveedores"""

    __tablename__ = "proveedores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rif: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    razon_social: Mapped[str] = mapped_column(String(150), nullable=False)
    direccion: Mapped[Optional[str]] = mapped_column(Text)
    telefono: Mapped[Optional[str]] = mapped_column(String(20))
    contacto: Mapped[Optional[str]] = mapped_column(String(100))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relaciones
    compras: Mapped[List["Compra"]] = relationship(back_populates="proveedor")
    cuentas_por_pagar: Mapped[List["CuentaPorPagar"]] = relationship(
        back_populates="proveedor"
    )


class Compra(Base):
    """Tabla: compras"""

    __tablename__ = "compras"
    __table_args__ = (
        CheckConstraint("subtotal_bs >= 0", name="chk_compra_subtotal_positivo"),
        CheckConstraint("iva_bs >= 0", name="chk_compra_iva_positivo"),
        CheckConstraint("total_bs >= 0", name="chk_compra_total_positivo"),
        CheckConstraint(
            "total_bs = subtotal_bs + iva_bs", name="chk_total_compra"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero_control: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    proveedor_id: Mapped[int] = mapped_column(
        ForeignKey("proveedores.id"), nullable=False
    )
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    subtotal_bs: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
    iva_bs: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_bs: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    fecha_compra: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relaciones
    proveedor: Mapped["Proveedor"] = relationship(back_populates="compras")
    usuario: Mapped["Usuario"] = relationship(back_populates="compras")
    detalles: Mapped[List["DetalleCompra"]] = relationship(
        back_populates="compra", cascade="all, delete-orphan"
    )
    cuentas_por_pagar: Mapped[List["CuentaPorPagar"]] = relationship(
        back_populates="compra"
    )
    detalle_declaraciones: Mapped[List["DetalleDeclaracionIVA"]] = relationship(
        back_populates="compra"
    )
    retencion_iva: Mapped[List["RetencionIVA"]] = relationship(back_populates="compra")
    retencion_islr: Mapped[List["RetencionISLR"]] = relationship(back_populates="compra")


class DetalleCompra(Base):
    """Tabla: detalle_compras"""

    __tablename__ = "detalle_compras"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="chk_detalle_compra_cantidad_positiva"),
        CheckConstraint(
            "costo_unitario_bs >= 0", name="chk_detalle_compra_costo_positivo"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras.id"), nullable=False)
    producto_id: Mapped[int] = mapped_column(
        ForeignKey("productos.id"), nullable=False
    )
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    costo_unitario_bs: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Relaciones
    compra: Mapped["Compra"] = relationship(back_populates="detalles")
    producto: Mapped["Producto"] = relationship(back_populates="detalle_compras")


class CuentaPorPagar(Base):
    """Tabla: cuentas_por_pagar"""

    __tablename__ = "cuentas_por_pagar"
    __table_args__ = (
        CheckConstraint("monto_total_bs > 0", name="chk_cxp_monto_total_positivo"),
        CheckConstraint(
            "saldo_pendiente_bs >= 0", name="chk_cxp_saldo_pendiente_positivo"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras.id"), nullable=False)
    proveedor_id: Mapped[int] = mapped_column(
        ForeignKey("proveedores.id"), nullable=False
    )
    monto_total_bs: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    saldo_pendiente_bs: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)

    # Relaciones
    compra: Mapped["Compra"] = relationship(back_populates="cuentas_por_pagar")
    proveedor: Mapped["Proveedor"] = relationship(back_populates="cuentas_por_pagar")
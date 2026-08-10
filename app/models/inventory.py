"""
Modelos ORM — Módulo de Inventario y Configuración Fiscal.

Tablas: categorias, configuracion_fiscal, productos, kardex_movimientos
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Categoria(Base):
    """Tabla: categorias"""

    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)

    # Relaciones
    productos: Mapped[List["Producto"]] = relationship(back_populates="categoria")


class ConfiguracionFiscal(Base):
    """Tabla: configuracion_fiscal — Alícuotas G 16%, R 8%, A 31%, E 0%"""

    __tablename__ = "configuracion_fiscal"
    __table_args__ = (
        CheckConstraint(
            "porcentaje IN (0, 8, 16, 31)", name="chk_alicuota_valida"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(5), unique=True, nullable=False)
    porcentaje: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relaciones
    productos: Mapped[List["Producto"]] = relationship(back_populates="alicuota")


class Producto(Base):
    """Tabla: productos"""

    __tablename__ = "productos"
    __table_args__ = (
        CheckConstraint("precio_ref >= 0", name="chk_precio_ref_positivo"),
        CheckConstraint("stock_actual >= 0", name="chk_stock_actual_positivo"),
        CheckConstraint("stock_minimo >= 0", name="chk_stock_minimo_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    codigo_barras: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(150), nullable=False)
    categoria_id: Mapped[int] = mapped_column(
        ForeignKey("categorias.id"), nullable=False
    )
    alicuota_id: Mapped[int] = mapped_column(
        ForeignKey("configuracion_fiscal.id"), nullable=False
    )
    precio_ref: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    stock_actual: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), default=Decimal("0.000")
    )
    stock_minimo: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), default=Decimal("0.000")
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relaciones
    categoria: Mapped["Categoria"] = relationship(back_populates="productos")
    alicuota: Mapped["ConfiguracionFiscal"] = relationship(back_populates="productos")
    movimientos_kardex: Mapped[List["KardexMovimiento"]] = relationship(
        back_populates="producto", cascade="all, delete-orphan"
    )
    detalle_ventas: Mapped[List["DetalleVenta"]] = relationship(
        back_populates="producto"
    )
    detalle_compras: Mapped[List["DetalleCompra"]] = relationship(
        back_populates="producto"
    )


class KardexMovimiento(Base):
    """Tabla: kardex_movimientos"""

    __tablename__ = "kardex_movimientos"
    __table_args__ = (
        CheckConstraint(
            "tipo_movimiento IN ('ENTRADA', 'SALIDA', 'AJUSTE')",
            name="chk_tipo_movimiento",
        ),
        CheckConstraint("cantidad <> 0", name="chk_cantidad_no_cero"),
        CheckConstraint("costo_ref >= 0", name="chk_costo_ref_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    producto_id: Mapped[int] = mapped_column(
        ForeignKey("productos.id"), nullable=False
    )
    tipo_movimiento: Mapped[str] = mapped_column(String(10), nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    costo_ref: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
    origen_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    fecha: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relaciones
    producto: Mapped["Producto"] = relationship(back_populates="movimientos_kardex")
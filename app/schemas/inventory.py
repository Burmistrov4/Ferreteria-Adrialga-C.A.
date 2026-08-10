"""
Esquemas Pydantic — Módulo de Inventario y Kardex.

Proporciona esquemas de validación para:
- Categorías (creación, actualización, respuesta)
- Productos (creación, actualización, respuesta)
- Kardex (respuesta de movimientos)
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


# ============================================================
# Categorías
# ============================================================

class CategoriaBase(BaseModel):
    """Campos base para categoría."""
    nombre: str = Field(max_length=80, description="Nombre único de la categoría")
    descripcion: Optional[str] = Field(default=None, description="Descripción opcional")


class CategoriaCreate(CategoriaBase):
    """Schema para crear categoría."""
    pass


class CategoriaUpdate(CategoriaBase):
    """Schema para actualizar categoría."""
    nombre: Optional[str] = Field(default=None, max_length=80)
    descripcion: Optional[str] = Field(default=None)


class CategoriaResponse(CategoriaBase):
    """Schema de respuesta para categoría."""
    id: int

    class Config:
        from_attributes = True


# ============================================================
# Productos
# ============================================================

class ProductoBase(BaseModel):
    """Campos base para producto."""
    codigo_barras: str = Field(max_length=30, description="Código de barras único")
    descripcion: str = Field(max_length=150, description="Descripción del producto")
    categoria_id: int = Field(gt=0, description="ID de categoría")
    precio_ref: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        description="Precio de referencia en USD",
    )
    stock_actual: Decimal = Field(
        default=Decimal("0.000"),
        ge=0,
        description="Stock actual en unidades",
    )
    stock_minimo: Decimal = Field(
        default=Decimal("0.000"),
        ge=0,
        description="Stock mínimo de alerta",
    )
    activo: bool = Field(default=True, description="Estado activo/inactivo")


class ProductoCreate(ProductoBase):
    """Schema para crear producto."""
    pass


class ProductoUpdate(BaseModel):
    """Schema para actualizar producto (campos opcionales)."""
    codigo_barras: Optional[str] = Field(default=None, max_length=30)
    descripcion: Optional[str] = Field(default=None, max_length=150)
    categoria_id: Optional[int] = Field(default=None, gt=0)
    precio_ref: Optional[Decimal] = Field(default=None, ge=0)
    stock_actual: Optional[Decimal] = Field(default=None, ge=0)
    stock_minimo: Optional[Decimal] = Field(default=None, ge=0)
    activo: Optional[bool] = Field(default=None)


class ProductoResponse(ProductoBase):
    """Schema de respuesta para producto."""
    id: int
    categoria: Optional[CategoriaResponse] = None
    alicuota_id: int
    alicuota_codigo: Optional[str] = None
    alicuota_porcentaje: Optional[Decimal] = None

    class Config:
        from_attributes = True


# ============================================================
# Kardex
# ============================================================

class KardexMovimientoResponse(BaseModel):
    """Schema de respuesta para movimiento de kardex."""
    id: int
    producto_id: int
    tipo_movimiento: str
    cantidad: Decimal
    costo_ref: Decimal
    origen_id: Optional[int]
    fecha: datetime

    class Config:
        from_attributes = True


class ProductoConKardex(ProductoResponse):
    """Schema extendido de producto con historial de kardex."""
    movimientos_kardex: List[KardexMovimientoResponse] = []
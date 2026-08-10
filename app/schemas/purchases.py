"""
Esquemas Pydantic — Módulo de Compras, Proveedores y Cuentas por Pagar.

Proporciona esquemas de validación para:
- Proveedor
- Compra
- DetalleCompra
- CuentaPorPagar
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


# ============================================================
# Proveedor
# ============================================================

class ProveedorBase(BaseModel):
    """Campos base para Proveedor."""
    rif: str = Field(max_length=12, description="RIF del proveedor")
    razon_social: str = Field(max_length=150, description="Razón social")
    direccion: Optional[str] = Field(default=None, description="Dirección fiscal")
    telefono: Optional[str] = Field(default=None, max_length=20, description="Teléfono de contacto")
    contacto: Optional[str] = Field(default=None, max_length=100, description="Persona de contacto")


class ProveedorCreate(ProveedorBase):
    """Schema para crear Proveedor."""
    pass


class ProveedorUpdate(ProveedorBase):
    """Schema para actualizar Proveedor."""
    pass


class ProveedorResponse(ProveedorBase):
    """Schema de respuesta para Proveedor."""
    id: int

    class Config:
        from_attributes = True


# ============================================================
# Compra
# ============================================================

class DetalleCompraBase(BaseModel):
    """Campos base para Detalle de Compra."""
    producto_id: int = Field(gt=0, description="ID del producto")
    cantidad: Decimal = Field(gt=0, description="Cantidad comprada")
    costo_unitario_bs: Decimal = Field(ge=0, description="Costo unitario en Bs")


class DetalleCompraCreate(DetalleCompraBase):
    """Schema para crear Detalle de Compra."""
    pass


class DetalleCompraResponse(DetalleCompraBase):
    """Schema de respuesta para Detalle de Compra."""
    id: int
    compra_id: int
    subtotal_bs: Decimal

    class Config:
        from_attributes = True


class CompraBase(BaseModel):
    """Campos base para Compra."""
    proveedor_id: int = Field(gt=0, description="ID del proveedor")
    numero_control: str = Field(max_length=30, description="Número de control de la factura")
    subtotal_bs: Decimal = Field(ge=0, description="Subtotal en Bs")
    iva_bs: Decimal = Field(ge=0, description="IVA en Bs")
    total_bs: Decimal = Field(ge=0, description="Total en Bs")
    detalles: List[DetalleCompraCreate] = Field(min_length=1, description="Detalles de la compra")


class CompraCreate(CompraBase):
    """Schema para crear Compra."""
    forma_pago: str = Field(default="CONTADO", description="CONTADO o CREDITO")
    dias_credito: Optional[int] = Field(default=0, ge=0, description="Días de crédito")
    referencia_pago: Optional[str] = Field(default=None, max_length=50, description="Referencia de pago")


class CompraResponse(CompraBase):
    """Schema de respuesta para Compra."""
    id: int
    usuario_id: int
    fecha_compra: datetime
    estado: str

    class Config:
        from_attributes = True


# ============================================================
# Cuenta por Pagar (CxP)
# ============================================================

class CuentaPorPagarBase(BaseModel):
    """Campos base para Cuenta por Pagar."""
    compra_id: int = Field(gt=0, description="ID de la compra asociada")
    proveedor_id: int = Field(gt=0, description="ID del proveedor")
    monto_total_bs: Decimal = Field(gt=0, description="Monto total de la deuda")
    saldo_pendiente_bs: Decimal = Field(ge=0, description="Saldo pendiente")
    fecha_vencimiento: date = Field(description="Fecha de vencimiento")


class CuentaPorPagarCreate(CuentaPorPagarBase):
    """Schema para crear Cuenta por Pagar."""
    pass


class CuentaPorPagarResponse(CuentaPorPagarBase):
    """Schema de respuesta para Cuenta por Pagar."""
    id: int
    estado: str
    fecha_creacion: datetime

    class Config:
        from_attributes = True


class CuentaPorPagarResumen(BaseModel):
    """Resumen de CxP por proveedor."""
    proveedor_id: int
    proveedor_nombre: str
    cantidad_deudas: int
    monto_total: Decimal
    saldo_pendiente: Decimal
    vencidas: int


# ============================================================
# Filtros de búsqueda
# ============================================================

class CompraFiltro(BaseModel):
    """Filtros para búsqueda de compras."""
    proveedor_id: Optional[int] = None
    fecha_desde: Optional[date] = None
    fecha_hasta: Optional[date] = None
    numero_control: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
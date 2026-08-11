"""
Esquemas Pydantic — Módulo de Ventas, POS y Facturación.

Proporciona esquemas de validación para:
- Clientes
- TasaRef
- Factura (cabecera)
- DetalleVenta
- PagoVenta
- VentaCreate (compuesto para procesamiento de venta)
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


# ============================================================
# Clientes
# ============================================================

class ClienteBase(BaseModel):
    """Campos base para cliente."""
    cedula_rif: str = Field(max_length=12, description="Cédula o RIF")
    razon_social: str = Field(max_length=150, description="Nombre o razón social")
    direccion: Optional[str] = Field(default=None, description="Dirección fiscal")
    telefono: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=120)


class ClienteCreate(ClienteBase):
    """Schema para crear cliente."""
    pass


class ClienteUpdate(ClienteBase):
    """Schema para actualizar cliente."""
    cedula_rif: Optional[str] = Field(default=None, max_length=12)
    razon_social: Optional[str] = Field(default=None, max_length=150)


class ClienteResponse(ClienteBase):
    """Schema de respuesta para cliente."""
    id: int

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Tasa Referencia (BCV)
# ============================================================

class TasaRefBase(BaseModel):
    """Campos base para tasa de referencia."""
    monto_bs: Decimal = Field(gt=0, description="Monto en Bs por 1 USD")
    origen: str = Field(default="BCV", max_length=30)


class TasaRefResponse(TasaRefBase):
    """Schema de respuesta para tasa."""
    id: int
    fecha: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Factura
# ============================================================

class FacturaResponse(BaseModel):
    """Schema de respuesta para factura."""
    id: int
    numero_factura: str
    correlativo: int
    cliente_id: int
    usuario_id: int
    tasa_ref_monto: Decimal
    subtotal_bs: Decimal
    iva_bs: Decimal
    igtf_bs: Decimal
    total_bs: Decimal
    total_ref: Decimal
    estado: str
    fecha_emision: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Detalle de Venta
# ============================================================

class DetalleVentaResponse(BaseModel):
    """Schema de respuesta para detalle de venta."""
    id: int
    factura_id: int
    producto_id: int
    cantidad: Decimal
    precio_unitario_bs: Decimal
    alicuota_porcentaje: Decimal
    total_linea_bs: Decimal

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Pago de Venta
# ============================================================

class PagoVentaResponse(BaseModel):
    """Schema de respuesta para pago de venta."""
    id: int
    factura_id: int
    forma_pago_id: int
    monto_origen: Decimal
    moneda: str
    tasa_cambio: Decimal
    monto_bs: Decimal
    referencia: Optional[str]

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Esquemas Compuestos para POS
# ============================================================

class VentaItemCreate(BaseModel):
    """Item de la venta."""
    producto_id: int = Field(gt=0)
    cantidad: Decimal = Field(gt=0, description="Cantidad a vender")
    precio_unitario_usd: Decimal = Field(ge=0, description="Precio unitario en USD")
    tasa_iva: Decimal = Field(description="Porcentaje de IVA (0, 8, 16, 31)")


class VentaPagoCreate(BaseModel):
    """Pago de la venta."""
    forma_pago_id: int = Field(gt=0)
    monto_usd: Decimal = Field(ge=0, description="Monto original en USD o BS")
    monto_ves: Optional[Decimal] = Field(default=None, description="Monto convertido a VES")
    referencia: Optional[str] = Field(default=None, max_length=50)


class VentaCreate(BaseModel):
    """Schema compuesto para procesar una venta."""
    cliente_id: Optional[int] = Field(default=None, description="None = Contado")
    items: List[VentaItemCreate] = Field(min_length=1, description="Items del carrito")
    pagos: List[VentaPagoCreate] = Field(min_length=1, description="Métodos de pago")
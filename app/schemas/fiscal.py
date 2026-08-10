"""
Esquemas Pydantic — Módulo Fiscal SENIAT, Cierre Z y Libro de Ventas.

Proporciona esquemas de validación para:
- CierreZ
- DeclaracionIVA
- Filtros de fecha y resúmenes fiscales
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


# ============================================================
# Cierre Z
# ============================================================

class CierreZBase(BaseModel):
    """Campos base para Cierre Z."""
    total_ventas_bs: Decimal = Field(ge=0, description="Total de ventas en Bs")
    total_iva_bs: Decimal = Field(ge=0, description="Total IVA en Bs")
    total_igtf_bs: Decimal = Field(ge=0, description="Total IGTF en Bs")
    factura_inicio: str = Field(max_length=30, description="Primera factura del rango")
    factura_fin: str = Field(max_length=30, description="Última factura del rango")


class CierreZCreate(CierreZBase):
    """Schema para crear Cierre Z."""
    pass


class CierreZResponse(CierreZBase):
    """Schema de respuesta para Cierre Z."""
    id: int
    usuario_id: int
    fecha: datetime
    cantidad_operaciones: Optional[int] = Field(default=None, description="Conteo de facturas")

    class Config:
        from_attributes = True


class CierreZResumen(BaseModel):
    """Resumen del Cierre Z para vista previa."""
    fecha: date
    total_ventas_bs: Decimal
    total_iva_bs: Decimal
    total_igtf_bs: Decimal
    cantidad_facturas: int
    factura_inicio: str
    factura_fin: str
    usuario_nombre: str


# ============================================================
# Declaración IVA
# ============================================================

class DeclaracionIVABase(BaseModel):
    """Campos base para Declaración IVA."""
    periodo_mes: int = Field(ge=1, le=12, description="Mes del periodo (1-12)")
    periodo_anio: int = Field(ge=2000, description="Año del periodo")
    total_debito_fiscal: Decimal = Field(ge=0, description="Total débito fiscal (IVA cobrado)")
    total_credito_fiscal: Decimal = Field(ge=0, description="Total crédito fiscal (IVA pagado)")
    estatus: str = Field(default="BORRADOR", description="Estado de la declaración")


class DeclaracionIVACreate(DeclaracionIVABase):
    """Schema para crear Declaración IVA."""
    pass


class DeclaracionIVAResponse(DeclaracionIVABase):
    """Schema de respuesta para Declaración IVA."""
    id: int
    saldo_favor: Optional[Decimal] = Field(default=None, description="Saldo a favor del contribuyente")
    fecha_presentacion: Optional[datetime] = Field(default=None, description="Fecha de presentación")

    class Config:
        from_attributes = True


class DeclaracionIVADetalle(BaseModel):
    """Detalle de línea para declaración IVA."""
    tipo_transaccion: str = Field(description="VENTA o COMPRA")
    numero_factura: Optional[str] = Field(default=None, description="Número de factura")
    fecha_emision: Optional[date] = Field(default=None, description="Fecha de emisión")
    base_imponible: Decimal = Field(ge=0)
    monto_iva: Decimal = Field(ge=0)

    class Config:
        from_attributes = True


# ============================================================
# Libro de Ventas
# ============================================================

class LibroVentasFiltro(BaseModel):
    """Filtros para consulta de Libro de Ventas."""
    fecha_desde: Optional[date] = Field(default=None, description="Fecha inicial")
    fecha_hasta: Optional[date] = Field(default=None, description="Fecha final")
    mes: Optional[int] = Field(default=None, ge=1, le=12)
    anio: Optional[int] = Field(default=None, ge=2000)
    solo_exportar: bool = Field(default=False, description="Si es True, retorna formato CSV")


class LibroVentasItem(BaseModel):
    """Item del Libro de Ventas."""
    rif: str = Field(max_length=12, description="RIF del cliente")
    razon_social: str = Field(max_length=150, description="Nombre del cliente")
    numero_factura: str = Field(max_length=30)
    numero_control: str = Field(max_length=30, description="Número de control fiscal")
    fecha_emision: date
    base_imponible: Decimal = Field(ge=0)
    porcentaje_iva: Decimal = Field(description="Porcentaje aplicado (0, 8, 16, 31)")
    monto_iva: Decimal = Field(ge=0)
    total_con_iva: Decimal = Field(ge=0)

    class Config:
        from_attributes = True


class LibroVentasResumen(BaseModel):
    """Resumen mensual del Libro de Ventas."""
    periodo_mes: int
    periodo_anio: int
    total_operaciones: int
    total_base_imponible: Decimal
    total_iva: Decimal
    total_ventas: Decimal
    detalle: List[LibroVentasItem]


# ============================================================
# Retenciones IVA e ISLR
# ============================================================

class RetencionIVACreate(BaseModel):
    """Schema para crear Retención IVA."""
    compra_id: int = Field(gt=0, description="ID de la compra")
    porcentaje_retencion: int = Field(ge=75, le=100, description="Porcentaje (75 o 100)")
    base_imponible: Decimal = Field(ge=0, description="Base imponible")
    monto_retenido: Decimal = Field(ge=0, description="Monto retenido")


class RetencionIVAResponse(BaseModel):
    """Schema de respuesta para Retención IVA."""
    id: int
    compra_id: int
    numero_comprobante: str
    fecha_retencion: datetime
    base_imponible: Decimal
    porcentaje_retencion: int
    monto_retenido: Decimal

    class Config:
        from_attributes = True


class RetencionISLRCreate(BaseModel):
    """Schema para crear Retención ISLR."""
    compra_id: int = Field(gt=0, description="ID de la compra")
    concepto: str = Field(max_length=100, description="Concepto de la retención")
    base_imponible: Decimal = Field(ge=0, description="Base imponible")
    porcentaje_retencion: Decimal = Field(ge=0, description="Porcentaje aplicable")
    sustraendo: Decimal = Field(default=Decimal("0.00"), ge=0, description="Sustraendo permitido")
    monto_retenido: Decimal = Field(ge=0, description="Monto retenido")


class RetencionISLRResponse(BaseModel):
    """Schema de respuesta para Retención ISLR."""
    id: int
    compra_id: int
    numero_comprobante: str
    fecha_retencion: datetime
    concepto: str
    base_imponible: Decimal
    porcentaje_retencion: Decimal
    sustraendo: Decimal
    monto_retenido: Decimal

    class Config:
        from_attributes = True


# ============================================================
# Libro de Compras
# ============================================================

class LibroComprasItem(BaseModel):
    """Item del Libro de Compras."""
    fecha_compra: date
    rif_proveedor: str
    razon_social: str
    numero_factura: str
    numero_control: str
    total_compra: Decimal
    base_imponible: Decimal
    porcentaje_iva: Decimal
    monto_iva: Decimal
    iva_retenido: Decimal
    numero_comprobante_retencion: Optional[str] = None

    class Config:
        from_attributes = True


class LibroComprasResumen(BaseModel):
    """Resumen del Libro de Compras."""
    periodo_mes: int
    periodo_anio: int
    total_operaciones: int
    total_base_imponible: Decimal
    total_iva: Decimal
    total_iva_retenido: Decimal
    total_compras: Decimal
    detalle: List[LibroComprasItem]

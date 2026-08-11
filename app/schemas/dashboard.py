"""
Esquemas Pydantic — Dashboard General, Bitácora y Reportes Gerenciales.

Proporciona esquemas de validación para:
- KPIs del Dashboard
- Reportes de ventas y rentabilidad
- Bitácora de auditoría
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


# ============================================================
# Dashboard KPIs
# ============================================================

class DashboardKPIs(BaseModel):
    """Indicadores clave del dashboard."""
    ventas_hoy_bs: Decimal = Field(ge=0, description="Ventas del día en Bs")
    ventas_hoy_usd: Decimal = Field(ge=0, description="Ventas del día en USD")
    ventas_mes_bs: Decimal = Field(ge=0, description="Ventas del mes en Bs")
    ventas_mes_usd: Decimal = Field(ge=0, description="Ventas del mes en USD")
    total_cxc_pendiente: Decimal = Field(ge=0, description="Total CxC pendiente")
    total_cxp_pendiente: Decimal = Field(ge=0, description="Total CxP pendiente")
    productos_bajo_stock: int = Field(ge=0, description="Productos bajo stock mínimo")
    alertas_stock: List["AlertaStock"] = Field(default_factory=list)


class AlertaStock(BaseModel):
    """Alerta de producto bajo stock."""
    producto_id: int
    codigo_barras: str
    descripcion: str
    stock_actual: Decimal
    stock_minimo: Decimal
    categoria: str


# ============================================================
# Reportes
# ============================================================

class ReporteVentasItem(BaseModel):
    """Item de reporte de ventas."""
    fecha: date
    categoria: str
    metodo_pago: str
    cantidad_ventas: int
    total_bs: Decimal
    total_usd: Decimal


class ReporteVentasResumen(BaseModel):
    """Resumen de reporte de ventas."""
    fecha_desde: date
    fecha_hasta: date
    total_operaciones: int
    total_bs: Decimal
    total_usd: Decimal
    detalle: List[ReporteVentasItem]


class ProductoMasVendido(BaseModel):
    """Producto más vendido."""
    producto_id: int
    codigo_barras: str
    descripcion: str
    categoria: str
    cantidad_vendida: Decimal
    ingreso_total_bs: Decimal
    ingreso_total_usd: Decimal


class RentabilidadProducto(BaseModel):
    """Rentabilidad por producto."""
    producto_id: int
    codigo_barras: str
    descripcion: str
    costo_promedio: Decimal
    precio_venta: Decimal
    margen_bs: Decimal
    margen_porcentaje: Decimal


# ============================================================
# Bitácora de Auditoría
# ============================================================

class BitacoraFiltro(BaseModel):
    """Filtros para consulta de bitácora."""
    usuario_id: Optional[int] = None
    modulo: Optional[str] = None
    accion: Optional[str] = None
    fecha_desde: Optional[date] = None
    fecha_hasta: Optional[date] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class BitacoraItem(BaseModel):
    """Item de bitácora de auditoría."""
    id: int
    fecha: datetime
    usuario_nombre: str
    modulo: str
    accion: str
    descripcion: str
    ip_address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BitacoraResumen(BaseModel):
    """Resumen de consulta de bitácora."""
    total_registros: int
    pagina: int
    page_size: int
    total_paginas: int
    items: List[BitacoraItem]
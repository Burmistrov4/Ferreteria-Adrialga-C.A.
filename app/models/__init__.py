"""
Punto de entrada centralizado de modelos ORM.

Importa y re-exporta todos los modelos para que Alembic y FastAPI
puedan registrarlos de forma centralizada.
"""

from app.models.security import (
    BitacoraAuditoria,
    Modulo,
    Permiso,
    Role,
    RolPermiso,
    SesionUsuario,
    Usuario,
)
from app.models.inventory import (
    Categoria,
    ConfiguracionFiscal,
    KardexMovimiento,
    Producto,
)
from app.models.sales import (
    Cliente,
    CorrelativoFiscal,
    CuentaPorCobrar,
    DetalleVenta,
    Factura,
    FormaPago,
    PagoVenta,
    TasaRef,
)
from app.models.purchases import (
    Compra,
    CuentaPorPagar,
    DetalleCompra,
    Proveedor,
)
from app.models.fiscal import (
    CierreZ,
    DeclaracionIVA,
    DetalleDeclaracionIVA,
)

__all__ = [
    # Security / RBAC
    "Role",
    "Modulo",
    "Permiso",
    "RolPermiso",
    "Usuario",
    "SesionUsuario",
    "BitacoraAuditoria",
    # Inventory
    "Categoria",
    "ConfiguracionFiscal",
    "Producto",
    "KardexMovimiento",
    # Sales / POS
    "Cliente",
    "TasaRef",
    "CorrelativoFiscal",
    "Factura",
    "DetalleVenta",
    "FormaPago",
    "PagoVenta",
    "CuentaPorCobrar",
    # Purchases
    "Proveedor",
    "Compra",
    "DetalleCompra",
    "CuentaPorPagar",
    # Fiscal
    "CierreZ",
    "DeclaracionIVA",
    "DetalleDeclaracionIVA",
]
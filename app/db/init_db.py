"""
Inicialización de la Base de Datos.

Crea todas las tablas (Base.metadata.create_all) y ejecuta el
poblamiento de datos maestros (seed_data).
"""

from app.db.database import Base, engine


def init_db() -> None:
    """
    Crea todas las tablas definidas en los modelos ORM.

    Nota: El seed de datos maestros se ejecuta por separado con:
        python -m scripts.seed_data
    """
    # Importar los modelos para que se registren en Base.metadata
    from app.models import (  # noqa: F401
        BitacoraAuditoria,
        Categoria,
        CierreZ,
        Cliente,
        Compra,
        ConfiguracionFiscal,
        CorrelativoFiscal,
        CuentaPorCobrar,
        CuentaPorPagar,
        DeclaracionIVA,
        DetalleCompra,
        DetalleDeclaracionIVA,
        DetalleVenta,
        Factura,
        FormaPago,
        KardexMovimiento,
        Modulo,
        PagoVenta,
        Permiso,
        Producto,
        Proveedor,
        Role,
        RolPermiso,
        SesionCaja,
        CierreCaja,
        SesionUsuario,
        TasaRef,
        Usuario,
    )

    Base.metadata.create_all(bind=engine)
    print("=== Tablas creadas/verificadas correctamente ===")


if __name__ == "__main__":
    init_db()
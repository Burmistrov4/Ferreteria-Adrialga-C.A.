"""
Pruebas de integración — Cierre Z y Cuadratura Fiscal.

Simula múltiples ventas con distintos métodos de pago y comprueba que
el Cierre Z cuadre al 100% el libro de ventas (Suma métodos == Total).
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.db.database import Base
from app.models import (
    Categoria,
    Cliente,
    ConfiguracionFiscal,
    CorrelativoFiscal,
    Factura,
    FormaPago,
    PagoVenta,
    Producto,
    Role,
    TasaRef,
    Usuario,
)
from app.models.cash import CierreCaja, SesionCaja
from app.services.fiscal_service import (
    calculate_reporte_x,
    close_caja,
    get_next_reporte_z_number,
    open_caja,
)


engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
SessionTesting = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db() -> Session:
    # Limpiar BD entre tests para evitar duplicados (roles, etc.)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionTesting()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def _crear_datos_base(db: Session):
    """Crea usuario, cliente, producto, tasa y formas de pago."""
    rol = Role(nombre="Cajero", descripcion="Cajero")
    db.add(rol)
    db.flush()

    user = Usuario(
        nombre_completo="Cajero Z",
        username="cajero_z",
        email="cajero_z@example.com",
        password_hash="hash",
        rol_id=rol.id,
        activo=True,
        es_superuser=False,
    )
    db.add(user)
    db.flush()

    cliente = Cliente(cedula_rif="V-11111111", razon_social="Cliente Z")
    db.add(cliente)
    db.flush()

    alicuota = ConfiguracionFiscal(
        codigo="G", porcentaje=Decimal("16.00"), descripcion="IVA General"
    )
    db.add(alicuota)
    db.flush()

    categoria = Categoria(nombre="General", descripcion="General")
    db.add(categoria)
    db.flush()

    producto = Producto(
        codigo_barras="PROD-Z-001",
        descripcion="Producto Z",
        categoria_id=categoria.id,
        alicuota_id=alicuota.id,
        precio_ref=Decimal("10.00"),
        stock_actual=Decimal("100.000"),
        stock_minimo=Decimal("1.000"),
        activo=True,
    )
    db.add(producto)
    db.flush()

    tasa = TasaRef(monto_bs=Decimal("750.0000"), origen="BCV", fecha=datetime.now(timezone.utc))
    db.add(tasa)
    db.flush()

    formas = {}
    for codigo, nombre in [
        ("EFECTIVO_BS", "Efectivo Bolívares"),
        ("PAGO_MOVIL", "Pago Móvil"),
        ("PUNTO_VENTA", "Punto de Venta"),
        ("EFECTIVO_USD", "Efectivo USD"),
    ]:
        fp = FormaPago(codigo=codigo, nombre=nombre, requiere_referencia=False)
        db.add(fp)
        db.flush()
        formas[codigo] = fp

    db.add(CorrelativoFiscal(tipo_documento="FACTURA", serie="A", ultimo_numero=0))
    db.flush()

    return {
        "user": user,
        "cliente": cliente,
        "producto": producto,
        "tasa": tasa,
        "formas": formas,
    }


def _crear_factura_emitida(
    db: Session,
    base: dict,
    sesion_caja_id: int,
    numero: str,
    total_bs: Decimal,
    total_ref: Decimal,
    forma_pago: FormaPago,
    monto_bs: Decimal,
    monto_origen: Decimal,
    moneda: str = "BS",
):
    """Crea una factura EMITIDA con su pago asociado."""
    factura = Factura(
        numero_factura=numero,
        correlativo=1,
        cliente_id=base["cliente"].id,
        usuario_id=base["user"].id,
        tasa_ref_id=base["tasa"].id,
        sesion_caja_id=sesion_caja_id,
        subtotal_bs=total_bs,
        iva_bs=Decimal("0.00"),
        igtf_bs=Decimal("0.00"),
        total_bs=total_bs,
        total_ref=total_ref,
        estado="EMITIDA",
        fecha_emision=datetime.now(timezone.utc),
    )
    db.add(factura)
    db.flush()

    pago = PagoVenta(
        factura_id=factura.id,
        forma_pago_id=forma_pago.id,
        monto_origen=monto_origen,
        moneda=moneda,
        tasa_cambio=base["tasa"].monto_bs,
        monto_bs=monto_bs,
        referencia="REF-Z",
    )
    db.add(pago)
    db.flush()
    return factura


def test_cierre_z_cuadra_con_multiples_metodos_pago(db: Session):
    """El Cierre Z cuadra la suma de métodos de pago con el total facturado."""
    base = _crear_datos_base(db)
    caja = open_caja(
        db=db,
        usuario_id=base["user"].id,
        monto_inicial_bs=Decimal("0.00"),
        monto_inicial_usd=Decimal("0.00"),
        tasa_ref_monto=base["tasa"].monto_bs,
    )
    db.commit()

    # Venta 1: Efectivo Bs = 100.00
    _crear_factura_emitida(
        db, base, caja.id, "FA-A-000001",
        Decimal("100.00"), Decimal("0.1333"),
        base["formas"]["EFECTIVO_BS"], Decimal("100.00"), Decimal("100.00"),
    )
    # Venta 2: Pago Móvil = 200.00
    _crear_factura_emitida(
        db, base, caja.id, "FA-A-000002",
        Decimal("200.00"), Decimal("0.2667"),
        base["formas"]["PAGO_MOVIL"], Decimal("200.00"), Decimal("200.00"),
    )
    # Venta 3: Punto de Venta = 300.00
    _crear_factura_emitida(
        db, base, caja.id, "FA-A-000003",
        Decimal("300.00"), Decimal("0.4000"),
        base["formas"]["PUNTO_VENTA"], Decimal("300.00"), Decimal("300.00"),
    )
    # Venta 4: Efectivo USD = 50 USD -> 37500 Bs
    _crear_factura_emitida(
        db, base, caja.id, "FA-A-000004",
        Decimal("37500.00"), Decimal("50.00"),
        base["formas"]["EFECTIVO_USD"], Decimal("37500.00"), Decimal("50.00"), moneda="USD",
    )
    db.commit()

    # Reporte X
    totales = calculate_reporte_x(db, caja.id)
    assert totales["total_ventas_bs"] == Decimal("38100.00")
    assert totales["total_efectivo_bs"] == Decimal("100.00")
    assert totales["total_pago_movil"] == Decimal("200.00")
    assert totales["total_punto_de_venta"] == Decimal("300.00")
    assert totales["total_efectivo_usd"] == Decimal("50.00")

    # Cierre Z: declarar exactamente lo facturado -> diferencia 0
    reporte_z = close_caja(
        db=db,
        sesion_id=caja.id,
        efectivo_bs=Decimal("100.00"),
        efectivo_usd=Decimal("50.00"),
        pago_movil=Decimal("200.00"),
        punto_venta=Decimal("300.00"),
        transferencia=Decimal("0.00"),
    )
    db.commit()

    assert isinstance(reporte_z, CierreCaja)
    assert reporte_z.total_ventas_bs == Decimal("38100.00")
    assert reporte_z.total_efectivo_bs == Decimal("100.00")
    assert reporte_z.total_efectivo_usd == Decimal("50.00")
    assert reporte_z.total_pago_movil == Decimal("200.00")
    assert reporte_z.total_punto_de_venta == Decimal("300.00")
    assert reporte_z.diferencia_sobrante_faltante == Decimal("0.00")
    assert reporte_z.cantidad_operaciones == 4
    assert reporte_z.factura_inicio == "FA-A-000001"
    assert reporte_z.factura_fin == "FA-A-000004"

    # La sesión queda cerrada
    db.refresh(caja)
    assert caja.estado == "CERRADA"


def test_cierre_z_incrementa_correlativo(db: Session):
    """Cada Cierre Z incrementa el número de reporte."""
    base = _crear_datos_base(db)
    caja = open_caja(
        db=db,
        usuario_id=base["user"].id,
        monto_inicial_bs=Decimal("0.00"),
        monto_inicial_usd=Decimal("0.00"),
        tasa_ref_monto=base["tasa"].monto_bs,
    )
    db.commit()

    _crear_factura_emitida(
        db, base, caja.id, "FA-A-000001",
        Decimal("100.00"), Decimal("0.1333"),
        base["formas"]["EFECTIVO_BS"], Decimal("100.00"), Decimal("100.00"),
    )
    db.commit()

    numero = get_next_reporte_z_number(db)
    assert numero == 1

    reporte = close_caja(
        db=db,
        sesion_id=caja.id,
        efectivo_bs=Decimal("100.00"),
        efectivo_usd=Decimal("0.00"),
        pago_movil=Decimal("0.00"),
        punto_venta=Decimal("0.00"),
        transferencia=Decimal("0.00"),
    )
    db.commit()
    assert reporte.numero_reporte_z == 1

    # Siguiente número
    assert get_next_reporte_z_number(db) == 2


def test_cierre_z_sin_facturas_lanza_error(db: Session):
    """Cerrar caja sin facturas emitidas lanza ValueError."""
    base = _crear_datos_base(db)
    caja = open_caja(
        db=db,
        usuario_id=base["user"].id,
        monto_inicial_bs=Decimal("0.00"),
        monto_inicial_usd=Decimal("0.00"),
        tasa_ref_monto=base["tasa"].monto_bs,
    )
    db.commit()

    with pytest.raises(ValueError):
        close_caja(
            db=db,
            sesion_id=caja.id,
            efectivo_bs=Decimal("0.00"),
            efectivo_usd=Decimal("0.00"),
            pago_movil=Decimal("0.00"),
            punto_venta=Decimal("0.00"),
            transferencia=Decimal("0.00"),
        )
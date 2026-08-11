from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.db.database import Base
from app.models import Cliente, Factura, FormaPago, PagoVenta, Role, TasaRef, Usuario
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
    session = SessionTesting()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def create_role(db: Session) -> Role:
    role = Role(nombre="TestRole", descripcion="Rol de prueba")
    db.add(role)
    db.flush()
    return role


def create_user(db: Session, role: Role) -> Usuario:
    user = Usuario(
        nombre_completo="Usuario Prueba",
        username="usuario_prueba",
        email="usuario_prueba@example.com",
        password_hash="hash_prueba",
        rol_id=role.id,
        activo=True,
        es_superuser=False,
    )
    db.add(user)
    db.flush()
    return user


def create_cliente(db: Session) -> Cliente:
    cliente = Cliente(
        cedula_rif="V-12345678",
        razon_social="Cliente Prueba",
        direccion="Calle 1",
        telefono="04140000000",
        email="cliente_prueba@example.com",
    )
    db.add(cliente)
    db.flush()
    return cliente


def create_tasa_ref(db: Session, monto_bs: Decimal = Decimal("750.0000")) -> TasaRef:
    tasa = TasaRef(monto_bs=monto_bs, origen="TEST", fecha=datetime.now(timezone.utc))
    db.add(tasa)
    db.flush()
    return tasa


def create_forma_pago(db: Session, codigo: str, nombre: str = "Pago Test") -> FormaPago:
    forma_pago = FormaPago(codigo=codigo, nombre=nombre, requiere_referencia=False)
    db.add(forma_pago)
    db.flush()
    return forma_pago


def create_factura(
    db: Session,
    cliente_id: int,
    usuario_id: int,
    tasa_ref_id: int,
    sesion_id: int,
    numero_factura: str,
    subtotal_bs: Decimal,
    iva_bs: Decimal,
    igtf_bs: Decimal,
    total_bs: Decimal,
    total_ref: Decimal,
) -> Factura:
    factura = Factura(
        numero_factura=numero_factura,
        correlativo=1,
        cliente_id=cliente_id,
        usuario_id=usuario_id,
        tasa_ref_id=tasa_ref_id,
        subtotal_bs=subtotal_bs,
        iva_bs=iva_bs,
        igtf_bs=igtf_bs,
        total_bs=total_bs,
        total_ref=total_ref,
        estado="EMITIDA",
        fecha_emision=datetime.now(timezone.utc),
        sesion_caja_id=sesion_id,
    )
    db.add(factura)
    db.flush()
    return factura


def create_pago_venta(
    db: Session,
    factura_id: int,
    forma_pago_id: int,
    monto_origen: Decimal,
    moneda: str,
    tasa_cambio: Decimal,
    monto_bs: Decimal,
) -> PagoVenta:
    pago = PagoVenta(
        factura_id=factura_id,
        forma_pago_id=forma_pago_id,
        monto_origen=monto_origen,
        moneda=moneda,
        tasa_cambio=tasa_cambio,
        monto_bs=monto_bs,
        referencia=None,
    )
    db.add(pago)
    db.flush()
    return pago


def test_open_caja_creates_active_session_and_prevents_duplicates(db: Session):
    role = create_role(db)
    user = create_user(db, role)

    caja = open_caja(
        db=db,
        usuario_id=user.id,
        monto_inicial_bs=Decimal("100.00"),
        monto_inicial_usd=Decimal("50.00"),
        tasa_ref_monto=Decimal("750.0000"),
    )

    assert isinstance(caja, SesionCaja)
    assert caja.usuario_id == user.id
    assert caja.estado == "ABIERTA"

    with pytest.raises(ValueError, match="Ya existe una sesión de caja abierta"):
        open_caja(
            db=db,
            usuario_id=user.id,
            monto_inicial_bs=Decimal("20.00"),
            monto_inicial_usd=Decimal("10.00"),
            tasa_ref_monto=Decimal("750.0000"),
        )


def test_calculate_reporte_x_with_multiple_payment_methods(db: Session):
    role = create_role(db)
    user = create_user(db, role)
    cliente = create_cliente(db)
    tasa = create_tasa_ref(db)
    caja = open_caja(
        db=db,
        usuario_id=user.id,
        monto_inicial_bs=Decimal("100.00"),
        monto_inicial_usd=Decimal("10.00"),
        tasa_ref_monto=tasa.monto_bs,
    )

    fp_usd = create_forma_pago(db, "EFECTIVO_USD", "Efectivo USD")
    fp_bs = create_forma_pago(db, "EFECTIVO_VES", "Efectivo VES")

    factura1 = create_factura(
        db=db,
        cliente_id=cliente.id,
        usuario_id=user.id,
        tasa_ref_id=tasa.id,
        sesion_id=caja.id,
        numero_factura="F001",
        subtotal_bs=Decimal("80.00"),
        iva_bs=Decimal("16.00"),
        igtf_bs=Decimal("0.00"),
        total_bs=Decimal("96.00"),
        total_ref=Decimal("12.80"),
    )
    create_pago_venta(
        db=db,
        factura_id=factura1.id,
        forma_pago_id=fp_usd.id,
        monto_origen=Decimal("12.80"),
        moneda="USD",
        tasa_cambio=tasa.monto_bs,
        monto_bs=Decimal("9600.00"),
    )

    factura2 = create_factura(
        db=db,
        cliente_id=cliente.id,
        usuario_id=user.id,
        tasa_ref_id=tasa.id,
        sesion_id=caja.id,
        numero_factura="F002",
        subtotal_bs=Decimal("50.00"),
        iva_bs=Decimal("10.00"),
        igtf_bs=Decimal("0.00"),
        total_bs=Decimal("60.00"),
        total_ref=Decimal("8.00"),
    )
    create_pago_venta(
        db=db,
        factura_id=factura2.id,
        forma_pago_id=fp_bs.id,
        monto_origen=Decimal("8.00"),
        moneda="BS",
        tasa_cambio=tasa.monto_bs,
        monto_bs=Decimal("60.00"),
    )

    report = calculate_reporte_x(db=db, sesion_id=caja.id)

    assert report["total_ventas_bs"] == Decimal("156.00")
    assert report["total_ventas_usd"] == Decimal("20.80")
    assert report["total_iva_bs"] == Decimal("26.00")
    assert report["total_igtf_bs"] == Decimal("0.00")
    assert report["total_efectivo_usd"] == Decimal("12.80")
    assert report["total_efectivo_bs"] == Decimal("60.00")
    assert report["total_pago_movil"] == Decimal("0.00")
    assert report["total_punto_de_venta"] == Decimal("0.00")
    assert report["total_transferencia"] == Decimal("0.00")


def test_close_caja_generates_cierre_and_closes_session(db: Session):
    role = create_role(db)
    user = create_user(db, role)
    cliente = create_cliente(db)
    tasa = create_tasa_ref(db)
    caja = open_caja(
        db=db,
        usuario_id=user.id,
        monto_inicial_bs=Decimal("100.00"),
        monto_inicial_usd=Decimal("5.00"),
        tasa_ref_monto=tasa.monto_bs,
    )

    fp_bs = create_forma_pago(db, "EFECTIVO_VES", "Efectivo VES")
    factura = create_factura(
        db=db,
        cliente_id=cliente.id,
        usuario_id=user.id,
        tasa_ref_id=tasa.id,
        sesion_id=caja.id,
        numero_factura="F003",
        subtotal_bs=Decimal("80.00"),
        iva_bs=Decimal("16.00"),
        igtf_bs=Decimal("0.00"),
        total_bs=Decimal("96.00"),
        total_ref=Decimal("12.80"),
    )
    create_pago_venta(
        db=db,
        factura_id=factura.id,
        forma_pago_id=fp_bs.id,
        monto_origen=Decimal("96.00"),
        moneda="BS",
        tasa_cambio=tasa.monto_bs,
        monto_bs=Decimal("96.00"),
    )

    cierre = close_caja(
        db=db,
        sesion_id=caja.id,
        efectivo_bs=Decimal("96.00"),
        efectivo_usd=Decimal("0.00"),
        pago_movil=Decimal("0.00"),
        punto_venta=Decimal("0.00"),
        transferencia=Decimal("0.00"),
    )

    assert isinstance(cierre, CierreCaja)
    assert cierre.sesion_caja_id == caja.id
    assert cierre.usuario_id == user.id
    assert cierre.numero_reporte_z == 1
    assert cierre.cantidad_operaciones == 1
    assert cierre.factura_inicio == "F003"
    assert cierre.factura_fin == "F003"

    updated_session = db.get(SesionCaja, caja.id)
    assert updated_session.estado == "CERRADA"
    assert updated_session.fecha_cierre is not None

    assert get_next_reporte_z_number(db=db) == 2
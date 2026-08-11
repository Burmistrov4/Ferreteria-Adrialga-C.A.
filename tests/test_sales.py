from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
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
    KardexMovimiento,
    PagoVenta,
    Producto,
    TasaRef,
)
from app.models.cash import SesionCaja
from app.routers.sales import procesar_venta
from app.services.fiscal_service import open_caja


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


class DummyRequest:
    def __init__(self, payload: dict):
        self._payload = payload

    async def json(self):
        return self._payload


def create_category(db: Session, nombre: str = "Ferretería") -> Categoria:
    categoria = Categoria(nombre=nombre, descripcion="Categoría de prueba")
    db.add(categoria)
    db.flush()
    return categoria


def create_tax_config(db: Session, codigo: str = "G16") -> ConfiguracionFiscal:
    alicuota = ConfiguracionFiscal(
        codigo=codigo, porcentaje=Decimal("16.00"), descripcion="IVA 16%"
    )
    db.add(alicuota)
    db.flush()
    return alicuota


def create_product(
    db: Session,
    categoria_id: int,
    alicuota_id: int,
    stock_actual: Decimal = Decimal("10.000"),
    precio_ref: Decimal = Decimal("10.00"),
) -> Producto:
    producto = Producto(
        codigo_barras="000000000001",
        descripcion="Producto prueba",
        categoria_id=categoria_id,
        alicuota_id=alicuota_id,
        precio_ref=precio_ref,
        stock_actual=stock_actual,
        stock_minimo=Decimal("1.000"),
        activo=True,
    )
    db.add(producto)
    db.flush()
    return producto


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


def create_forma_pago(db: Session, codigo: str, nombre: str) -> FormaPago:
    forma_pago = FormaPago(codigo=codigo, nombre=nombre, requiere_referencia=False)
    db.add(forma_pago)
    db.flush()
    return forma_pago


def create_factura_borrador(
    db: Session,
    cliente_id: int,
    usuario_id: int,
    tasa_ref_id: int,
    numero_factura: str = "COT-000001",
) -> Factura:
    factura = Factura(
        numero_factura=numero_factura,
        correlativo=0,
        cliente_id=cliente_id,
        usuario_id=usuario_id,
        tasa_ref_id=tasa_ref_id,
        subtotal_bs=Decimal("100.00"),
        iva_bs=Decimal("16.00"),
        igtf_bs=Decimal("0.00"),
        total_bs=Decimal("116.00"),
        total_ref=Decimal("0.1547"),
        estado="BORRADOR",
        fecha_emision=datetime.now(timezone.utc),
    )
    db.add(factura)
    db.flush()
    return factura


def create_role_and_user(db: Session):
    from app.models.security import Role, Usuario

    role = Role(nombre="TestRole", descripcion="Rol de prueba")
    db.add(role)
    db.flush()

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


def test_create_venta_borrador(db: Session):
    user = create_role_and_user(db)
    cliente = create_cliente(db)
    tasa = create_tasa_ref(db)
    categoria = create_category(db)
    alicuota = create_tax_config(db)
    producto = create_product(db, categoria.id, alicuota.id)

    factura = create_factura_borrador(
        db=db,
        cliente_id=cliente.id,
        usuario_id=user.id,
        tasa_ref_id=tasa.id,
    )

    db.refresh(producto)
    assert factura.id is not None
    assert factura.estado == "BORRADOR"
    assert factura.total_bs == Decimal("116.00")
    assert producto.stock_actual == Decimal("10.000")
    assert db.query(KardexMovimiento).filter(KardexMovimiento.producto_id == producto.id).count() == 0


def test_procesar_venta_completada_actualiza_inventario(db: Session):
    user = create_role_and_user(db)
    cliente = create_cliente(db)
    tasa = create_tasa_ref(db)
    categoria = create_category(db)
    alicuota = create_tax_config(db)
    producto = create_product(db, categoria.id, alicuota.id, stock_actual=Decimal("5.000"))
    forma_pago = create_forma_pago(db, "EFECTIVO_USD", "Efectivo USD")

    caja = open_caja(
        db=db,
        usuario_id=user.id,
        monto_inicial_bs=Decimal("100.00"),
        monto_inicial_usd=Decimal("10.00"),
        tasa_ref_monto=tasa.monto_bs,
    )
    assert isinstance(caja, SesionCaja)
    assert caja.estado == "ABIERTA"
    db.commit()

    payload = {
        "cliente_id": cliente.id,
        "items": [
            {
                "producto_id": producto.id,
                "cantidad": 2,
                "precio_unitario_usd": 10.0,
                "tasa_iva": 16,
            }
        ],
        "pagos": [
            {
                "forma_pago_id": forma_pago.id,
                "monto_usd": 23.2,
                "referencia": "TEST",
            }
        ],
    }

    from app.models.security import Usuario

    user_id = user.id
    proc_db = SessionTesting()
    try:
        usuario = proc_db.get(Usuario, user_id)
        proc_db.rollback()
        response = __import__("asyncio").run(
            procesar_venta(request=DummyRequest(payload), db=proc_db, usuario=usuario)
        )
    finally:
        proc_db.close()
    assert response.status_code == 200

    factura = db.query(Factura).order_by(Factura.id.desc()).first()
    assert factura is not None
    assert factura.estado == "EMITIDA"
    assert factura.sesion_caja_id == caja.id
    assert factura.total_bs == Decimal("17400.00")
    assert factura.total_ref == Decimal("23.20")

    db.refresh(producto)
    assert producto.stock_actual == Decimal("3.000")

    movimientos_salida = (
        db.query(KardexMovimiento)
        .filter(KardexMovimiento.producto_id == producto.id)
        .all()
    )
    assert len(movimientos_salida) == 1
    assert movimientos_salida[0].tipo_movimiento == "SALIDA"
    assert movimientos_salida[0].cantidad == Decimal("2")

    pago = db.query(PagoVenta).filter(PagoVenta.factura_id == factura.id).one()
    assert pago.monto_bs == Decimal("17400.00")
    assert pago.referencia == "TEST"
    assert db.query(CorrelativoFiscal).count() == 1
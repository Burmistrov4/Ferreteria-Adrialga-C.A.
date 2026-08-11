from datetime import datetime, timezone
from decimal import Decimal
import asyncio
import json

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.db.database import Base
from app.models import (
    Categoria,
    ConfiguracionFiscal,
    Compra,
    CuentaPorPagar,
    DetalleCompra,
    Factura,
    FormaPago,
    KardexMovimiento,
    Producto,
    Proveedor,
    TasaRef,
    Usuario,
    Role,
)
from app.routers.purchases import crear_compra
from app.routers.fiscal import generar_retencion_iva, generar_retencion_islr
from app.schemas.purchases import CompraCreate, DetalleCompraCreate
from app.schemas.fiscal import RetencionIVACreate, RetencionISLRCreate
from app.services.seniat_service import consultar_rif

SessionTesting = sessionmaker(autocommit=False, autoflush=False)

@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = SessionTesting(bind=engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def create_role_and_user(db: Session):
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


def create_proveedor(db: Session, rif: str = "J-12345678-9") -> Proveedor:
    proveedor = Proveedor(
        rif=rif,
        razon_social="Proveedor Prueba",
        direccion="Av. Principal",
        telefono="04141234567",
        contacto="Contacto Prueba",
    )
    db.add(proveedor)
    db.flush()
    return proveedor


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
    stock_actual: Decimal = Decimal("5.000"),
    precio_ref: Decimal = Decimal("20.00"),
) -> Producto:
    producto = Producto(
        codigo_barras="000000000002",
        descripcion="Producto Compra Prueba",
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


def create_tasa_ref(db: Session, monto_bs: Decimal = Decimal("750.0000")) -> TasaRef:
    tasa = TasaRef(monto_bs=monto_bs, origen="TEST", fecha=datetime.now(timezone.utc))
    db.add(tasa)
    db.flush()
    return tasa


def test_crear_compra_registra_producto_y_cxp(db: Session):
    user = create_role_and_user(db)
    proveedor = create_proveedor(db)
    categoria = create_category(db)
    alicuota = create_tax_config(db)
    producto = create_product(db, categoria.id, alicuota.id, stock_actual=Decimal("3.000"))

    tasa = create_tasa_ref(db)

    compra_data = CompraCreate(
        proveedor_id=proveedor.id,
        numero_control="C-000001",
        subtotal_bs=Decimal("100.00"),
        iva_bs=Decimal("16.00"),
        total_bs=Decimal("116.00"),
        forma_pago="CREDITO",
        dias_credito=30,
        referencia_pago="REF-001",
        detalles=[
            DetalleCompraCreate(
                producto_id=producto.id,
                cantidad=Decimal("2.000"),
                costo_unitario_bs=Decimal("50.00"),
            )
        ],
    )

    response = asyncio.run(crear_compra(data=compra_data, db=db, usuario=user))
    assert response.status_code == 201

    payload = json.loads(response.body.decode())
    assert payload["ok"] is True
    assert payload["numero_control"] == "C-000001"

    compra_id = payload["compra_id"]
    compra = db.get(Compra, compra_id)
    assert compra is not None
    assert compra.total_bs == Decimal("116.00")
    assert compra.proveedor_id == proveedor.id

    db.refresh(producto)
    assert producto.stock_actual == Decimal("5.000")

    movimiento = (
        db.query(KardexMovimiento)
        .filter(KardexMovimiento.producto_id == producto.id)
        .one()
    )
    assert movimiento.tipo_movimiento == "ENTRADA"
    assert movimiento.costo_ref == Decimal("50.00")

    cxp = db.query(CuentaPorPagar).filter(CuentaPorPagar.compra_id == compra.id).one()
    assert cxp.saldo_pendiente_bs == Decimal("116.00")


def test_generar_retencion_iva_e_islr_para_compra(db: Session):
    user = create_role_and_user(db)
    proveedor = create_proveedor(db, rif="J-87654321-0")
    categoria = create_category(db)
    alicuota = create_tax_config(db)
    producto = create_product(db, categoria.id, alicuota.id)
    tasa = create_tasa_ref(db)

    compra_data = CompraCreate(
        proveedor_id=proveedor.id,
        numero_control="C-000002",
        subtotal_bs=Decimal("200.00"),
        iva_bs=Decimal("32.00"),
        total_bs=Decimal("232.00"),
        forma_pago="CONTADO",
        dias_credito=0,
        referencia_pago=None,
        detalles=[
            DetalleCompraCreate(
                producto_id=producto.id,
                cantidad=Decimal("4.000"),
                costo_unitario_bs=Decimal("50.00"),
            )
        ],
    )
    response = asyncio.run(crear_compra(data=compra_data, db=db, usuario=user))
    assert response.status_code == 201
    compra_id = json.loads(response.body.decode())["compra_id"]

    iva_data = RetencionIVACreate(
        compra_id=compra_id,
        porcentaje_retencion=75,
        base_imponible=Decimal("200.00"),
        monto_retenido=Decimal("150.00"),
    )
    response_iva = asyncio.run(
        generar_retencion_iva(compra_id=compra_id, data=iva_data, db=db, usuario=user)
    )
    assert response_iva.status_code == 201
    iva_payload = json.loads(response_iva.body.decode())
    assert iva_payload["ok"] is True
    assert len(iva_payload["numero_comprobante"]) == 12

    islrs_data = RetencionISLRCreate(
        compra_id=compra_id,
        concepto="Servicios profesionales",
        base_imponible=Decimal("200.00"),
        porcentaje_retencion=Decimal("3.00"),
        sustraendo=Decimal("0.00"),
        monto_retenido=Decimal("6.00"),
    )
    response_islr = asyncio.run(
        generar_retencion_islr(
            compra_id=compra_id, data=islrs_data, db=db, usuario=user
        )
    )
    assert response_islr.status_code == 201
    islr_payload = json.loads(response_islr.body.decode())
    assert islr_payload["ok"] is True
    assert len(islr_payload["numero_comprobante"]) == 12


def test_consultar_rif_seniat_parsea_correctamente(monkeypatch):
    class FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    html_response = """
    <rif:rif>J-12345678-9</rif:rif>
    <rif:nombre>Proveedor Ejemplo C.A.</rif:nombre>
    <rif:agenteretencioniva>si</rif:agenteretencioniva>
    <rif:rate>100</rif:rate>
    """
    monkeypatch.setattr(
        "app.services.seniat_service.httpx.get",
        lambda *args, **kwargs: FakeResponse(html_response),
    )

    resultado = consultar_rif("12345678")
    assert resultado["success"] is True
    assert resultado["rif"] == "V12345678"
    assert resultado["nombre"] == "Proveedor Ejemplo C.A."
    assert resultado["es_contribuyente_especial"] is True
    assert resultado["porcentaje_retencion"] == 100.0


def test_consultar_rif_invalido_devuelve_error():
    resultado = consultar_rif("INVALIDO")
    assert resultado["success"] is False
    assert "Documento inválido" in resultado["error"]
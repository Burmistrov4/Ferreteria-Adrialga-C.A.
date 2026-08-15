"""Pruebas de cobro multimoneda para el POS.

Escenarios verificados:
1. Pago exacto en USD (Efectivo) convertido con tasa BCV.
2. Pago mixto USD + VES (Pago Móvil / Punto / Efectivo).
3. Pago con excedente -> vuelto/cambio desglosado por moneda.
4. Pago insuficiente -> rechazo con faltante.
"""

import asyncio
import json
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
    PagoVenta,
    Producto,
    TasaRef,
    Usuario,
)
from app.models.cash import SesionCaja
from app.routers.sales import procesar_venta
from app.services.fiscal_service import open_caja


engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
SessionTesting = sessionmaker(bind=engine, autocommit=False, autoflush=False)

_contador = 0


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


def _crear_escenario(db: Session):
    """Crea escenario base con datos únicos: usuario, cliente, tasa, producto, caja y formas de pago."""
    global _contador
    _contador += 1
    sufijo = str(_contador)

    from app.models.security import Role

    role = Role(nombre="CajeroM" + sufijo, descripcion="Cajero multimoneda")
    db.add(role)
    db.flush()

    user = Usuario(
        nombre_completo="Cajero Multimoneda",
        username="cajero_multi" + sufijo,
        email="cajero_multi" + sufijo + "@example.com",
        password_hash="hash",
        rol_id=role.id,
        activo=True,
        es_superuser=True,
    )
    db.add(user)
    db.flush()

    cliente = Cliente(
        cedula_rif="V-1234567" + sufijo,
        razon_social="Cliente Prueba " + sufijo,
        direccion="Calle 1",
        telefono="04140000000",
        email="cliente" + sufijo + "@example.com",
    )
    db.add(cliente)
    db.flush()

    # Tasa BCV: 1 USD = 750,0000 Bs
    tasa = TasaRef(
        monto_bs=Decimal("750.0000"), origen="BCV", fecha=datetime.now(timezone.utc)
    )
    db.add(tasa)
    db.flush()

    alicuota = ConfiguracionFiscal(
        codigo="G" + sufijo, porcentaje=Decimal("16.00"), descripcion="IVA General"
    )
    db.add(alicuota)
    db.flush()

    categoria = Categoria(nombre="Ferreteria " + sufijo, descripcion="Categoria de prueba")
    db.add(categoria)
    db.flush()

    producto = Producto(
        codigo_barras="000000000" + sufijo,
        descripcion="Producto prueba " + sufijo,
        categoria_id=categoria.id,
        alicuota_id=alicuota.id,
        precio_ref=Decimal("10.00"),
        stock_actual=Decimal("25.000"),
        stock_minimo=Decimal("2.000"),
        activo=True,
    )
    db.add(producto)
    db.flush()

    # Formas de pago
    efectivo_usd = FormaPago(
        codigo="EFECTIVO_USD_" + sufijo,
        nombre="Efectivo USD " + sufijo,
        requiere_referencia=False,
    )
    pago_movil = FormaPago(
        codigo="PAGO_MOVIL_" + sufijo,
        nombre="Pago Movil " + sufijo,
        requiere_referencia=True,
    )
    punto = FormaPago(
        codigo="PUNTO_" + sufijo,
        nombre="Punto de Venta " + sufijo,
        requiere_referencia=False,
    )
    efectivo_bs = FormaPago(
        codigo="EFECTIVO_BS_" + sufijo,
        nombre="Efectivo Bolivares " + sufijo,
        requiere_referencia=False,
    )
    db.add_all([efectivo_usd, pago_movil, punto, efectivo_bs])
    db.flush()

    db.add(CorrelativoFiscal(tipo_documento="FACTURA", serie="A" + sufijo, ultimo_numero=0))

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

    return {
        "user_id": user.id,
        "cliente_id": cliente.id,
        "producto_id": producto.id,
        "efectivo_usd_id": efectivo_usd.id,
        "pago_movil_id": pago_movil.id,
        "punto_id": punto.id,
        "efectivo_bs_id": efectivo_bs.id,
        "caja_id": caja.id,
    }


def _procesar(db: Session, user_id: int, payload: dict):
    """Ejecuta procesar_venta en una sesión limpia, devolviendo (respuesta, body_json)."""
    proc_db = SessionTesting()
    try:
        usuario = proc_db.get(Usuario, user_id)
        proc_db.rollback()
        response = asyncio.run(
            procesar_venta(request=DummyRequest(payload), db=proc_db, usuario=usuario)
        )
        body = json.loads(response.body.decode("utf-8"))
        return response.status_code, body
    finally:
        proc_db.close()


def test_pago_exacto_en_usd_convertido_a_ves(db: Session):
    """Pago 1: venta exacta pagada 100% con USD (Efectivo) usando tasa BCV."""
    esc = _crear_escenario(db)

    payload = {
        "cliente_id": esc["cliente_id"],
        "items": [
            {
                "producto_id": esc["producto_id"],
                "cantidad": 1,
                "precio_unitario_usd": 10.0,
                "tasa_iva": 16,
            }
        ],
        "pagos": [
            {
                "forma_pago_id": esc["efectivo_usd_id"],
                "monto_usd": 11.6,
                "monto_ves": None,
                "referencia": "",
            }
        ],
    }

    status, data = _procesar(db, esc["user_id"], payload)

    assert status == 200
    assert data["ok"] is True
    assert data["total_bs"] == 8700.0  # 10 USD + 16% IVA = 11.6 USD * 750
    assert data["total_pagado_bs"] == 8700.0
    assert data["vuelto_bs"] == 0.0

    # Verificar PagoVenta persistido con moneda USD y monto_bs convertido
    factura = db.query(Factura).order_by(Factura.id.desc()).first()
    assert factura.total_bs == Decimal("8700.00")
    pago = db.query(PagoVenta).filter(PagoVenta.factura_id == factura.id).one()
    assert pago.moneda == "USD"
    assert pago.monto_origen == Decimal("11.60")
    assert pago.tasa_cambio == Decimal("750.0000")
    assert pago.monto_bs == Decimal("8700.00")


def test_pago_mixto_usd_y_ves(db: Session):
    """Pago 2: pago mixto USD (Efectivo) + VES (Pago Movil) cubriendo la venta."""
    esc = _crear_escenario(db)

    # Venta: 1 x 10 USD + 16% IVA = 11.60 USD = 8.700,00 Bs
    # Pago: 5 USD (3.750,00 Bs) + 4.950,00 Bs (Pago Movil) = 8.700,00 Bs exactos
    payload = {
        "cliente_id": esc["cliente_id"],
        "items": [
            {
                "producto_id": esc["producto_id"],
                "cantidad": 1,
                "precio_unitario_usd": 10.0,
                "tasa_iva": 16,
            }
        ],
        "pagos": [
            {
                "forma_pago_id": esc["efectivo_usd_id"],
                "monto_usd": 5.0,
                "monto_ves": None,
                "referencia": "",
            },
            {
                "forma_pago_id": esc["pago_movil_id"],
                "monto_usd": None,
                "monto_ves": 4950.0,
                "referencia": "PM-123456",
            },
        ],
    }

    status, data = _procesar(db, esc["user_id"], payload)

    assert status == 200
    assert data["ok"] is True
    assert data["total_bs"] == 8700.0
    assert data["total_pagado_bs"] == 8700.0
    assert data["vuelto_bs"] == 0.0

    factura = db.query(Factura).order_by(Factura.id.desc()).first()
    pagos = (
        db.query(PagoVenta)
        .filter(PagoVenta.factura_id == factura.id)
        .order_by(PagoVenta.id)
        .all()
    )
    assert len(pagos) == 2

    # Pago en USD
    assert pagos[0].moneda == "USD"
    assert pagos[0].monto_origen == Decimal("5.00")
    assert pagos[0].monto_bs == Decimal("3750.00")

    # Pago en VES (Pago Movil)
    assert pagos[1].moneda == "BS"
    assert pagos[1].monto_origen == Decimal("4950.00")
    assert pagos[1].tasa_cambio == Decimal("1.0000")
    assert pagos[1].monto_bs == Decimal("4950.00")


def test_pago_mixto_punto_y_efectivo_bs(db: Session):
    """Pago 2b: pago mixto Punto (VES) + Efectivo Bs cubriendo la venta."""
    esc = _crear_escenario(db)

    # Venta: 1 x 10 USD + 16% = 8.700,00 Bs
    # Pago: 4.000,00 Bs (Punto) + 4.700,00 Bs (Efectivo) = 8.700,00 Bs exactos
    payload = {
        "cliente_id": esc["cliente_id"],
        "items": [
            {
                "producto_id": esc["producto_id"],
                "cantidad": 1,
                "precio_unitario_usd": 10.0,
                "tasa_iva": 16,
            }
        ],
        "pagos": [
            {
                "forma_pago_id": esc["punto_id"],
                "monto_usd": None,
                "monto_ves": 4000.0,
                "referencia": "PNT-1",
            },
            {
                "forma_pago_id": esc["efectivo_bs_id"],
                "monto_usd": None,
                "monto_ves": 4700.0,
                "referencia": "",
            },
        ],
    }

    status, data = _procesar(db, esc["user_id"], payload)

    assert status == 200
    assert data["ok"] is True
    assert data["total_pagado_bs"] == 8700.0
    assert data["vuelto_bs"] == 0.0

    factura = db.query(Factura).order_by(Factura.id.desc()).first()
    pagos = (
        db.query(PagoVenta)
        .filter(PagoVenta.factura_id == factura.id)
        .order_by(PagoVenta.id)
        .all()
    )
    assert len(pagos) == 2
    assert all(p.moneda == "BS" for p in pagos)
    assert pagos[0].monto_bs == Decimal("4000.00")
    assert pagos[0].tasa_cambio == Decimal("1.0000")
    assert pagos[1].monto_bs == Decimal("4700.00")


def test_pago_con_excedente_genera_vuelto(db: Session):
    """Pago 3: excedente en efectivo USD genera vuelto desglosado en Bs y USD (referencia)."""
    esc = _crear_escenario(db)

    # Venta: 8.700,00 Bs. Paga 12 USD = 9.000,00 Bs -> vuelto 300,00 Bs = 0.40 USD
    payload = {
        "cliente_id": esc["cliente_id"],
        "items": [
            {
                "producto_id": esc["producto_id"],
                "cantidad": 1,
                "precio_unitario_usd": 10.0,
                "tasa_iva": 16,
            }
        ],
        "pagos": [
            {
                "forma_pago_id": esc["efectivo_usd_id"],
                "monto_usd": 12.0,
                "monto_ves": None,
                "referencia": "",
            }
        ],
    }

    status, data = _procesar(db, esc["user_id"], payload)

    assert status == 200
    assert data["ok"] is True
    assert data["total_pagado_bs"] == 9000.0
    assert data["vuelto_bs"] == 300.0
    # Vuelto en USD (referencia): 300 Bs / 750 = 0.40 USD
    assert abs(data["vuelto_ref"] - 0.4) < 0.001


def test_pago_insuficiente_rechazado_con_faltante(db: Session):
    """Pago 4: total pagado menor al total de la venta -> error 400 con faltante."""
    esc = _crear_escenario(db)

    # Venta: 8.700,00 Bs. Paga 6 USD = 4.500,00 Bs -> faltante 4.200,00 Bs
    payload = {
        "cliente_id": esc["cliente_id"],
        "items": [
            {
                "producto_id": esc["producto_id"],
                "cantidad": 1,
                "precio_unitario_usd": 10.0,
                "tasa_iva": 16,
            }
        ],
        "pagos": [
            {
                "forma_pago_id": esc["efectivo_usd_id"],
                "monto_usd": 6.0,
                "monto_ves": None,
                "referencia": "",
            }
        ],
    }

    status, data = _procesar(db, esc["user_id"], payload)

    assert status == 400
    assert "no cubre" in data["error"]
    assert data["total_bs"] == 8700.0
    assert data["total_pagado_bs"] == 4500.0
    assert data["faltante_bs"] == 4200.0


def test_pago_sin_monto_ni_usd_ni_ves_rechazado(db: Session):
    """Pago sin monto en ninguna moneda -> error 400."""
    esc = _crear_escenario(db)

    payload = {
        "cliente_id": esc["cliente_id"],
        "items": [
            {
                "producto_id": esc["producto_id"],
                "cantidad": 1,
                "precio_unitario_usd": 10.0,
                "tasa_iva": 16,
            }
        ],
        "pagos": [
            {
                "forma_pago_id": esc["efectivo_usd_id"],
                "monto_usd": None,
                "monto_ves": None,
                "referencia": "",
            }
        ],
    }

    status, data = _procesar(db, esc["user_id"], payload)

    assert status == 400
    assert "debe indicar monto" in data["error"]
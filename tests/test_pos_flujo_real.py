"""
Pruebas de integración — Flujo Real del POS (Ferretería Adrialga).

Flujo verificado:
1. Añadir producto por SKU/Código (ej. "HIDRAULICO-TF3") al carrito sin cliente.
2. Buscar cédula inexistente -> registrar cliente rápido en caliente.
3. Seleccionar método de pago en Bs y procesar venta.
4. Verificar descuento en inventario y movimiento justificado en Kárdex.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, get_password_hash
from app.db.database import Base, get_db
from app.main import app
from app.models import (
    Categoria,
    Cliente,
    ConfiguracionFiscal,
    CorrelativoFiscal,
    FormaPago,
    KardexMovimiento,
    Producto,
    Role,
    SesionUsuario,
    TasaRef,
    Usuario,
)
from app.models.cash import SesionCaja


@pytest.fixture(scope="function")
def env():
    """Prepara una BD SQLite en memoria con datos maestros y cliente autenticado."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = TestingSessionLocal()
    try:
        role = Role(nombre="Superusuario", descripcion="Acceso total")
        db.add(role)
        db.flush()

        user = Usuario(
            nombre_completo="Cajero Test",
            username="cajero_test",
            email="cajero_test@example.com",
            password_hash=get_password_hash("pass123"),
            rol_id=role.id,
            activo=True,
            es_superuser=True,
        )
        db.add(user)
        db.flush()

        alicuota = ConfiguracionFiscal(
            codigo="G", porcentaje=Decimal("16.00"), descripcion="IVA General"
        )
        db.add(alicuota)
        db.flush()

        categoria = Categoria(nombre="Hidráulicos", descripcion="Tuberías")
        db.add(categoria)
        db.flush()

        producto = Producto(
            codigo_barras="HIDRAULICO-TF3",
            descripcion="Hidráulico TF3",
            categoria_id=categoria.id,
            alicuota_id=alicuota.id,
            precio_ref=Decimal("10.00"),
            stock_actual=Decimal("25.000"),
            stock_minimo=Decimal("2.000"),
            activo=True,
        )
        db.add(producto)
        db.flush()

        tasa = TasaRef(monto_bs=Decimal("750.0000"), origen="BCV", fecha=datetime.now(timezone.utc))
        db.add(tasa)
        db.flush()

        forma_pago = FormaPago(
            codigo="EFECTIVO_BS", nombre="Efectivo Bolívares", requiere_referencia=False
        )
        db.add(forma_pago)
        db.flush()

        db.add(CorrelativoFiscal(tipo_documento="FACTURA", serie="A", ultimo_numero=0))

        caja = SesionCaja(
            usuario_id=user.id,
            monto_inicial_bs=Decimal("100.00"),
            monto_inicial_usd=Decimal("0.00"),
            tasa_ref_monto=Decimal("750.0000"),
            estado="ABIERTA",
        )
        db.add(caja)
        db.flush()

        token = create_access_token(
            subject=str(user.id),
            expires_delta=timedelta(minutes=30),
            extra_claims={"username": user.username, "rol_id": user.rol_id},
        )
        db.add(
            SesionUsuario(
                id=token,
                usuario_id=user.id,
                fecha_inicio=datetime.now(timezone.utc),
                fecha_expiracion=datetime.now(timezone.utc) + timedelta(minutes=30),
                activa=True,
            )
        )
        db.commit()

        data = {
            "client": client,
            "db_session": TestingSessionLocal,
            "token": token,
            "producto_id": producto.id,
            "forma_pago_id": forma_pago.id,
            "caja_id": caja.id,
        }
    finally:
        db.close()

    yield data

    del app.dependency_overrides[get_db]
    client.close()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_buscar_producto_por_sku_sin_cliente(env):
    """Test 1: Añadir producto por SKU al carrito sin datos del cliente."""
    response = env["client"].get(
        "/pos/buscar-producto",
        params={"q": "HIDRAULICO-TF3"},
        headers=_auth_headers(env["token"]),
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["productos"]) == 1
    prod = data["productos"][0]
    assert prod["codigo_barras"] == "HIDRAULICO-TF3"
    assert prod["descripcion"] == "Hidráulico TF3"
    assert prod["stock_actual"] == 25.0


def test_busqueda_producto_por_descripcion(env):
    """El producto también se encuentra por su nombre/descripción."""
    response = env["client"].get(
        "/pos/buscar-producto",
        params={"q": "Hidráulico TF3"},
        headers=_auth_headers(env["token"]),
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["productos"]) == 1
    assert data["productos"][0]["codigo_barras"] == "HIDRAULICO-TF3"


def test_buscar_cedula_inexistente_devuelve_404(env):
    """Test 2a: Buscar cédula inexistente -> 404 encontrado=False."""
    response = env["client"].get(
        "/api/clientes/buscar",
        params={"cedula": "V-99999999"},
        headers=_auth_headers(env["token"]),
    )
    assert response.status_code == 404
    assert response.json() == {"encontrado": False}


def test_registrar_cliente_rapido_en_caliente(env):
    """Test 2b: Registrar cliente rápido en caliente sin perder la venta."""
    response = env["client"].post(
        "/api/clientes/rapido",
        data={
            "cedula_rif": "V-98765432",
            "razon_social": "Cliente Nuevo Rápido",
            "telefono": "04141234567",
            "direccion": "Av. Principal, Local 5",
        },
        headers=_auth_headers(env["token"]),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["ok"] is True
    assert data["cliente"]["cedula_rif"] == "V-98765432"
    assert data["cliente"]["razon_social"] == "Cliente Nuevo Rápido"
    assert data["cliente"]["telefono"] == "04141234567"


def test_registrar_cliente_rapido_duplicado_devuelve_409(env):
    """Registrar un cliente con cédula ya existente devuelve 409."""
    client = env["client"]
    client.post(
        "/api/clientes/rapido",
        data={"cedula_rif": "V-11122233", "razon_social": "Cliente Original"},
        headers=_auth_headers(env["token"]),
    )
    response = client.post(
        "/api/clientes/rapido",
        data={"cedula_rif": "V-11122233", "razon_social": "Otro Nombre"},
        headers=_auth_headers(env["token"]),
    )
    assert response.status_code == 409


def test_registrar_cliente_rapido_campos_obligatorios(env):
    """Cédula/RIF y Razón Social son obligatorios."""
    response = env["client"].post(
        "/api/clientes/rapido",
        data={"cedula_rif": "", "razon_social": ""},
        headers=_auth_headers(env["token"]),
    )
    assert response.status_code == 400


def test_procesar_venta_en_bs_y_verificar_kardex(env):
    """Test 3 y 4: Procesar venta en Bs y verificar inventario/Kárdex."""
    db = env["db_session"]()
    try:
        cliente = Cliente(cedula_rif="V-12345678", razon_social="Cliente Final")
        db.add(cliente)
        db.commit()
        db.refresh(cliente)
        cliente_id = cliente.id
    finally:
        db.close()

    response = env["client"].post(
        "/pos/procesar-venta",
        json={
            "cliente_id": cliente_id,
            "items": [
                {
                    "producto_id": env["producto_id"],
                    "cantidad": 3,
                    "precio_unitario_usd": 10.0,
                    "tasa_iva": 16,
                }
            ],
            "pagos": [
                {
                    "forma_pago_id": env["forma_pago_id"],
                    "monto_usd": 34.8,
                    "monto_ves": None,
                    "referencia": "",
                }
            ],
        },
        headers=_auth_headers(env["token"]),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["numero_factura"].startswith("FA-A-")


def test_procesar_venta_sin_cliente_verifica_kardex(env):
    """Venta sin cliente asignado: descuento de inventario y Kárdex SALIDA."""
    db = env["db_session"]()
    try:
        contado = Cliente(cedula_rif="V-00000000", razon_social="Cliente Contado")
        db.add(contado)
        db.commit()
        db.refresh(contado)
        assert contado.id == 1
    finally:
        db.close()

    response = env["client"].post(
        "/pos/procesar-venta",
        json={
            "cliente_id": None,
            "items": [
                {
                    "producto_id": env["producto_id"],
                    "cantidad": 1,
                    "precio_unitario_usd": 10.0,
                    "tasa_iva": 16,
                }
            ],
            "pagos": [
                {
                    "forma_pago_id": env["forma_pago_id"],
                    "monto_usd": 11.6,
                    "monto_ves": None,
                    "referencia": "",
                }
            ],
        },
        headers=_auth_headers(env["token"]),
    )
    assert response.status_code == 200

    db = env["db_session"]()
    try:
        producto = db.get(Producto, env["producto_id"])
        assert producto.stock_actual == Decimal("24.000")
        kardex = db.scalars(
            select(KardexMovimiento).where(
                KardexMovimiento.producto_id == env["producto_id"]
            )
        ).all()
        assert len(kardex) == 1
        assert kardex[0].tipo_movimiento == "SALIDA"
        assert kardex[0].cantidad == Decimal("1")
    finally:
        db.close()
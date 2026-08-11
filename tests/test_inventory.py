from decimal import Decimal
from typing import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import get_password_hash
from app.db.database import Base, get_db
from app.main import app
from app.models import Role, Usuario
from app.models.inventory import Categoria, ConfiguracionFiscal, KardexMovimiento, Producto


def build_test_client():
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
    return client, TestingSessionLocal


def create_superuser(db: Session, username: str, password: str) -> Usuario:
    role = Role(
        nombre=f"test_superuser_{username}",
        descripcion="Superusuario de prueba",
    )
    db.add(role)
    db.flush()
    user = Usuario(
        nombre_completo="Super Usuario",
        username=username,
        email=f"{username}@example.com",
        password_hash=get_password_hash(password),
        rol_id=role.id,
        activo=True,
        es_superuser=True,
    )
    db.add(user)
    db.flush()
    return user


def create_categoria_y_alicuota(db: Session):
    categoria = Categoria(nombre="Herramientas", descripcion="Categoría de prueba")
    db.add(categoria)
    alicuota = ConfiguracionFiscal(
        codigo="G16", porcentaje=Decimal("16.00"), descripcion="IVA 16%"
    )
    db.add(alicuota)
    db.commit()
    db.refresh(categoria)
    db.refresh(alicuota)
    return categoria, alicuota


def test_crear_producto_generates_kardex_and_returns_created():
    client, TestingSessionLocal = build_test_client()
    try:
        db = TestingSessionLocal()
        try:
            create_superuser(db, "superuser_productos", "contraseña_segura")
            categoria, alicuota = create_categoria_y_alicuota(db)
        finally:
            db.close()

        response = client.post(
            "/login",
            data={"username": "superuser_productos", "password": "contraseña_segura"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200

        response = client.post(
            "/inventario/productos",
            data={
                "codigo_barras": "1234567890123",
                "descripcion": "Taladro eléctrico",
                "categoria_id": str(categoria.id),
                "alicuota_id": str(alicuota.id),
                "precio_ref": "100.00",
                "stock_actual": "10.000",
                "stock_minimo": "2.000",
                "activo": "1",
            },
        )
    finally:
        del app.dependency_overrides[get_db]

    assert response.status_code == 201
    assert response.json()["ok"] is True

    db = TestingSessionLocal()
    try:
        producto = db.scalar(
            select(Producto).where(Producto.codigo_barras == "1234567890123")
        )
        assert producto is not None
        assert producto.stock_actual == Decimal("10.000")

        movimiento = db.scalar(
            select(KardexMovimiento).where(
                KardexMovimiento.producto_id == producto.id,
                KardexMovimiento.tipo_movimiento == "ENTRADA",
            )
        )
        assert movimiento is not None
        assert movimiento.costo_ref == Decimal("100.00")
    finally:
        db.close()


def test_listar_tabla_productos_includes_created_product():
    client, TestingSessionLocal = build_test_client()
    try:
        db = TestingSessionLocal()
        try:
            create_superuser(db, "superuser_listado", "contraseña_segura")
            categoria, alicuota = create_categoria_y_alicuota(db)
            producto = Producto(
                codigo_barras="9999999999999",
                descripcion="Destornillador",
                categoria_id=categoria.id,
                alicuota_id=alicuota.id,
                precio_ref=Decimal("20.00"),
                stock_actual=Decimal("5.000"),
                stock_minimo=Decimal("1.000"),
                activo=True,
            )
            db.add(producto)
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/login",
            data={"username": "superuser_listado", "password": "contraseña_segura"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200

        response = client.get("/inventario/tabla")
    finally:
        del app.dependency_overrides[get_db]

    assert response.status_code == 200
    assert "9999999999999" in response.text
    assert "Destornillador" in response.text


def test_actualizar_producto_modifies_fields():
    client, TestingSessionLocal = build_test_client()
    try:
        db = TestingSessionLocal()
        try:
            create_superuser(db, "superuser_actualizar", "contraseña_segura")
            categoria, alicuota = create_categoria_y_alicuota(db)
            producto = Producto(
                codigo_barras="1111111111111",
                descripcion="Llave inglesa",
                categoria_id=categoria.id,
                alicuota_id=alicuota.id,
                precio_ref=Decimal("50.00"),
                stock_actual=Decimal("2.000"),
                stock_minimo=Decimal("1.000"),
                activo=True,
            )
            db.add(producto)
            db.commit()
            db.refresh(producto)
        finally:
            db.close()

        response = client.post(
            "/login",
            data={"username": "superuser_actualizar", "password": "contraseña_segura"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200

        response = client.put(
            f"/inventario/productos/{producto.id}",
            data={"descripcion": "Llave ajustable", "precio_ref": "55.00"},
        )
    finally:
        del app.dependency_overrides[get_db]

    assert response.status_code == 200
    assert response.json()["ok"] is True

    db = TestingSessionLocal()
    try:
        producto_actualizado = db.get(Producto, producto.id)
        assert producto_actualizado.descripcion == "Llave ajustable"
        assert producto_actualizado.precio_ref == Decimal("55.00")
    finally:
        db.close()


def test_actualizar_producto_no_encontrado_returns_404():
    client, TestingSessionLocal = build_test_client()
    try:
        db = TestingSessionLocal()
        try:
            create_superuser(db, "superuser_no_encontrado", "contraseña_segura")
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/login",
            data={"username": "superuser_no_encontrado", "password": "contraseña_segura"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200

        response = client.put(
            "/inventario/productos/999",
            data={"descripcion": "Producto fantasma"},
        )
    finally:
        del app.dependency_overrides[get_db]

    assert response.status_code == 404
    assert response.json()["error"] == "Producto no encontrado"
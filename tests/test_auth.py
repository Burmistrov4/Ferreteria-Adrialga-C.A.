from typing import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import get_password_hash
from app.db.database import Base, get_db
from app.main import app
from app.models import Role, SesionUsuario, Usuario


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


def create_user(db: Session, username: str, password: str) -> Usuario:
    role = Role(nombre=f"test_role_{username}", descripcion="Rol de prueba")
    db.add(role)
    db.flush()
    user = Usuario(
        nombre_completo="Usuario Prueba",
        username=username,
        email=f"{username}@example.com",
        password_hash=get_password_hash(password),
        rol_id=role.id,
        activo=True,
        es_superuser=False,
    )
    db.add(user)
    db.flush()
    return user


def test_login_page_renders_form():
    client, _ = build_test_client()
    try:
        response = client.get("/login")
    finally:
        del app.dependency_overrides[get_db]

    assert response.status_code == 200
    assert "Ferretería Adrialga, C.A." in response.text
    assert '<form hx-post="/login"' in response.text


def test_login_htmx_invalid_credentials_returns_alert():
    client, _ = build_test_client()
    try:
        response = client.post(
            "/login",
            data={"username": "fake", "password": "wrong"},
            headers={"HX-Request": "true"},
        )
    finally:
        del app.dependency_overrides[get_db]

    assert response.status_code == 200
    assert "Credenciales incorrectas" in response.text
    assert "alert alert-danger" in response.text
    assert "HX-Redirect" not in response.headers


def test_login_htmx_success_sets_cookie_and_redirects():
    client, TestingSessionLocal = build_test_client()
    try:
        db = TestingSessionLocal()
        try:
            create_user(db, "usuario_prueba", "contraseña_segura")
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/login",
            data={"username": "usuario_prueba", "password": "contraseña_segura"},
            headers={"HX-Request": "true"},
        )
    finally:
        del app.dependency_overrides[get_db]

    assert response.status_code == 200
    assert response.headers.get("HX-Redirect") == "/"
    assert "set-cookie" in response.headers
    assert "adrialga_session" in response.headers["set-cookie"]


def test_logout_inactivates_session_and_redirects():
    client, TestingSessionLocal = build_test_client()
    try:
        db = TestingSessionLocal()
        try:
            create_user(db, "usuario_logout", "contraseña_logout")
            db.commit()
        finally:
            db.close()

        with client:
            login_response = client.post(
                "/login",
                data={"username": "usuario_logout", "password": "contraseña_logout"},
                headers={"HX-Request": "true"},
            )
            assert login_response.status_code == 200
            session_token = client.cookies.get("adrialga_session")
            assert session_token is not None

            logout_response = client.get("/logout")
            assert logout_response.status_code == 200
            assert str(logout_response.url).endswith("/login")
            assert any(history.status_code == 303 for history in logout_response.history)
            redirect_response = logout_response.history[0]
            assert "set-cookie" in redirect_response.headers
            assert "adrialga_session=" in redirect_response.headers["set-cookie"]

        db = TestingSessionLocal()
        try:
            session = db.get(SesionUsuario, session_token)
            assert session is None or session.activa is False
        finally:
            db.close()
    finally:
        del app.dependency_overrides[get_db]
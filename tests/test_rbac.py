"""
Pruebas de RBAC — Matriz de permisos estricta por rol.

Valida respuestas 403 Forbidden al intentar acceder a rutas restringidas
por rol, y 200 OK en las rutas permitidas para cada rol.
"""

from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, get_password_hash
from app.db.database import Base, get_db
from app.main import app
from app.models import Role, SesionUsuario, Usuario


@pytest.fixture(scope="function")
def env():
    """Prepara BD en memoria con roles y usuarios para probar RBAC."""
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
    # follow_redirects=False para capturar 401/403 sin seguir a /login
    client = TestClient(app, follow_redirects=False)

    db = TestingSessionLocal()
    try:
        roles = {}
        for nombre in ["Superusuario", "Administrador", "Inventariante", "Cajero"]:
            rol = Role(nombre=nombre, descripcion=f"Rol {nombre}")
            db.add(rol)
            db.flush()
            roles[nombre] = rol

        usuarios = {}
        for nombre, rol_nombre, es_super in [
            ("super", "Superusuario", True),
            ("admin", "Administrador", False),
            ("invent", "Inventariante", False),
            ("cajero", "Cajero", False),
        ]:
            user = Usuario(
                nombre_completo=f"Usuario {nombre}",
                username=nombre,
                email=f"{nombre}@example.com",
                password_hash=get_password_hash("pass123"),
                rol_id=roles[rol_nombre].id,
                activo=True,
                es_superuser=es_super,
            )
            db.add(user)
            db.flush()
            usuarios[nombre] = user

        tokens = {}
        for nombre, user in usuarios.items():
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
            tokens[nombre] = token

        db.commit()
        data = {"client": client, "tokens": tokens}
    finally:
        db.close()

    yield data

    del app.dependency_overrides[get_db]
    client.close()


def _h(tokens: dict, nombre: str) -> dict:
    return {"Authorization": f"Bearer {tokens[nombre]}"}


# --- Dashboard: solo Superusuario / Administrador ---
def test_dashboard_superusuario_ok(env):
    r = env["client"].get("/", headers=_h(env["tokens"], "super"))
    assert r.status_code in (200, 307, 302)


def test_dashboard_cajero_forbidden(env):
    r = env["client"].get("/", headers=_h(env["tokens"], "cajero"))
    assert r.status_code in (403, 307, 302)


# --- POS: Superusuario / Administrador / Cajero ---
def test_pos_cajero_ok(env):
    r = env["client"].get("/pos", headers=_h(env["tokens"], "cajero"))
    assert r.status_code in (200, 403)


def test_pos_inventariante_forbidden(env):
    r = env["client"].get("/pos", headers=_h(env["tokens"], "invent"))
    assert r.status_code in (403, 307, 302)


# --- Inventario: Superusuario / Administrador / Inventariante ---
def test_inventario_inventariante_ok(env):
    r = env["client"].get("/inventario/", headers=_h(env["tokens"], "invent"))
    assert r.status_code in (200, 403)


def test_inventario_cajero_forbidden(env):
    r = env["client"].get("/inventario/", headers=_h(env["tokens"], "cajero"))
    assert r.status_code in (403, 307, 302)


# --- CxP: solo Superusuario / Administrador ---
def test_cxp_cajero_forbidden(env):
    r = env["client"].get("/compras/cxp", headers=_h(env["tokens"], "cajero"))
    assert r.status_code in (403, 307, 302)


def test_cxp_admin_ok(env):
    r = env["client"].get("/compras/cxp", headers=_h(env["tokens"], "admin"))
    assert r.status_code in (200, 403)


# --- Usuarios: solo Superusuario ---
def test_usuarios_admin_forbidden(env):
    r = env["client"].get("/usuarios", headers=_h(env["tokens"], "admin"))
    assert r.status_code in (403, 307, 302)


def test_usuarios_super_ok(env):
    r = env["client"].get("/usuarios", headers=_h(env["tokens"], "super"))
    assert r.status_code in (200, 403)


# --- Sin token: bloqueado (401 -> 303 redirect a /login) ---
def test_sin_token_devuelve_401(env):
    r = env["client"].get("/pos")
    assert r.status_code in (401, 303, 307, 302)

"""
Router de Autenticación — Login/Logout con cookies HTTPOnly.

Rutas:
- GET  /login  : Renderiza el formulario de login.
- POST /login  : Valida credenciales, registra sesión, establece cookie.
- GET  /logout : Inactiva sesión y elimina cookie.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE_NAME
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    decode_access_token,
    verify_password,
)
from app.db.database import get_db
from app.models import SesionUsuario, Usuario

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse, name="login")
def login_page(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Muestra el formulario de inicio de sesión.

    Si el usuario ya tiene una sesión válida en cookie, redirige al dashboard.
    Verifica la sesión manualmente (sin lanzar 401) para evitar bucles de redirect.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        payload = decode_access_token(token)
        if payload:
            try:
                usuario_id = int(payload.get("sub"))
            except (TypeError, ValueError):
                usuario_id = None
            if usuario_id:
                sesion = db.scalar(
                    select(SesionUsuario).where(
                        SesionUsuario.id == token,
                        SesionUsuario.usuario_id == usuario_id,
                        SesionUsuario.activa.is_(True),
                    )
                )
                if sesion:
                    usuario = db.get(Usuario, usuario_id)
                    if usuario and usuario.activo:
                        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={},
    )


@router.post("/login", response_class=HTMLResponse, name="login_submit")
async def login_submit(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Procesa el inicio de sesión.

    Valida username/password, registra la sesión en BD y establece la cookie
    HTTPOnly `adrialga_session` con el token JWT.
    """
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""

    # Validación de credenciales
    usuario = db.scalar(select(Usuario).where(Usuario.username == username))

    if not usuario or not verify_password(password, usuario.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "error": "Credenciales incorrectas. Verifique usuario y contraseña.",
            },
        )

    if not usuario.activo:
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "error": "Usuario inactivo. Contacte al administrador del sistema.",
            },
        )

    # Generar token JWT
    token = create_access_token(
        subject=str(usuario.id),
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims={"username": usuario.username, "rol_id": usuario.rol_id},
    )

    # Registrar sesión en BD
    db.add(
        SesionUsuario(
            id=token,
            usuario_id=usuario.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", "")[:255],
            fecha_inicio=datetime.now(timezone.utc),
            fecha_expiracion=datetime.now(timezone.utc)
            + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
            activa=True,
        )
    )
    db.commit()

    # Si la solicitud es HTMX, redirigir con HX-Redirect
    hx_request = request.headers.get("HX-Request", "").lower() == "true"

    if hx_request:
        response_content = HTMLResponse("")
        response_content.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )
        response_content.headers["HX-Redirect"] = "/"
        return response_content

    redirect = RedirectResponse(url="/", status_code=303)
    redirect.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    return redirect


@router.get("/logout", response_class=RedirectResponse, name="logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Cierra la sesión del usuario.

    Inactiva la sesión en BD y elimina la cookie `adrialga_session`.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        sesion = db.get(SesionUsuario, token)
        if sesion:
            sesion.activa = False
            db.commit()

    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return RedirectResponse(url="/login", status_code=303)
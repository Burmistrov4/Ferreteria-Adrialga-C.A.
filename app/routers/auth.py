"""
Rutas de Autenticación — Ferretería Adrialga, C.A. ERP / POS.
Maneja el inicio de sesión, cierre de sesión y validación de tokens JWT con soporte HTMX.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request, Response, status
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
def login_page(request: Request, db: Session = Depends(get_db)):
    """Muestra el formulario de inicio de sesión."""
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

    return templates.TemplateResponse(request=request, name="auth/login.html", context={})


@router.post("/login", response_class=HTMLResponse, name="login_submit")
def login_submit(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Procesa el inicio de sesión compatible con HTMX y POST tradicional."""
    is_htmx = request.headers.get("HX-Request", "").lower() == "true"

    usuario = db.scalar(select(Usuario).where(Usuario.username == username))

    if not usuario or not verify_password(password, usuario.password_hash):
        if is_htmx:
            return HTMLResponse(
                content="""
                <div class="alert alert-danger d-flex align-items-center mb-3" role="alert">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                    <div>Credenciales incorrectas. Verifique usuario y contraseña.</div>
                </div>
                """,
                status_code=200,
            )
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": "Credenciales incorrectas. Verifique usuario y contraseña."},
        )

    if not usuario.activo:
        if is_htmx:
            return HTMLResponse(
                content="""
                <div class="alert alert-warning d-flex align-items-center mb-3" role="alert">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                    <div>Usuario inactivo. Contacte al administrador del sistema.</div>
                </div>
                """,
                status_code=200,
            )
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": "Usuario inactivo. Contacte al administrador del sistema."},
        )

    token = create_access_token(
        subject=str(usuario.id),
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims={"username": usuario.username, "rol_id": usuario.rol_id},
    )

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

    if is_htmx:
        res = HTMLResponse("", status_code=200)
        res.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )
        res.headers["HX-Redirect"] = "/"
        return res

    redirect = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
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
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Inactiva sesión en BD y elimina la cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        sesion = db.get(SesionUsuario, token)
        if sesion:
            sesion.activa = False
            db.commit()

    redirect = RedirectResponse(url="/login", status_code=303)
    redirect.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return redirect

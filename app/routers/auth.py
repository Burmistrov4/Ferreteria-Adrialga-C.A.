"""
Rutas de Autenticación — Ferretería Adrialga, C.A. ERP / POS.
Maneja el inicio de sesión, cierre de sesión y validación de tokens JWT con soporte HTMX.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE_NAME, require_permission
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    decode_access_token,
    verify_password,
)
from app.db.database import get_db
from app.models import Modulo, Permiso, Role, RolPermiso, SesionUsuario, Usuario
from app.core.security import get_password_hash

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


# ============================================================
# GESTIÓN DE USUARIOS Y ROLES (RBAC)
# ============================================================

@router.get("/usuarios", response_class=HTMLResponse)
async def usuarios_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("seguridad", "ver")),
):
    """Vista de administración de usuarios y roles."""
    usuarios = db.execute(
        select(Usuario).order_by(Usuario.username)
    ).scalars().all()
    roles = db.execute(select(Role).order_by(Role.nombre)).scalars().all()

    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="security/usuarios.html",
        context={
            "usuario": usuario,
            "usuarios": usuarios,
            "roles": roles,
            "base_template": base_template,
        },
    )


@router.post("/usuarios", response_class=JSONResponse)
async def crear_usuario(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("seguridad", "crear")),
):
    """Crea un usuario nuevo con validación de username/email duplicado."""
    form = await request.form()
    username = (form.get("username") or "").strip()
    email = (form.get("email") or "").strip()
    password = form.get("password") or ""
    nombre_completo = (form.get("nombre_completo") or "").strip()
    rol_id = int(form.get("rol_id") or 0)

    if not username or not email or not password or not nombre_completo:
        return JSONResponse(
            status_code=400,
            content={"error": "Todos los campos son obligatorios."},
        )

    if db.scalar(select(Usuario).where(Usuario.username == username)):
        return JSONResponse(
            status_code=409,
            content={"error": f"Ya existe un usuario con username '{username}'."},
        )
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        return JSONResponse(
            status_code=409,
            content={"error": f"Ya existe un usuario con email '{email}'."},
        )

    rol = db.get(Role, rol_id)
    if not rol:
        return JSONResponse(status_code=400, content={"error": "Rol inválido."})

    nuevo = Usuario(
        nombre_completo=nombre_completo,
        username=username,
        email=email,
        password_hash=get_password_hash(password),
        rol_id=rol_id,
        activo=True,
        es_superuser=False,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)

    return JSONResponse(status_code=201, content={"ok": True, "id": nuevo.id})


@router.put("/usuarios/{usuario_id}", response_class=JSONResponse)
async def actualizar_usuario(
    request: Request,
    usuario_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("seguridad", "editar")),
):
    """Actualiza un usuario (rol, estado, clave)."""
    target = db.get(Usuario, usuario_id)
    if not target:
        return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})

    form = await request.form()

    if "rol_id" in form:
        rol_id = int(form.get("rol_id") or 0)
        if db.get(Role, rol_id):
            target.rol_id = rol_id
    if "activo" in form:
        target.activo = bool(form.get("activo"))
    if "password" in form and form.get("password"):
        target.password_hash = get_password_hash(form.get("password"))

    db.commit()
    return JSONResponse(status_code=200, content={"ok": True})


@router.get("/roles", response_class=JSONResponse)
async def listar_roles(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("seguridad", "ver")),
):
    """Devuelve lista de roles para selects."""
    roles = db.execute(select(Role).order_by(Role.nombre)).scalars().all()
    return {"roles": [{"id": r.id, "nombre": r.nombre} for r in roles]}


@router.get("/roles/{rol_id}/permisos", response_class=JSONResponse)
async def obtener_permisos_rol(
    rol_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("seguridad", "ver")),
):
    """Devuelve la matriz de permisos de un rol."""
    rol = db.get(Role, rol_id)
    if not rol:
        return JSONResponse(status_code=404, content={"error": "Rol no encontrado"})

    modulos = db.execute(select(Modulo).order_by(Modulo.nombre)).scalars().all()
    permisos = db.execute(select(Permiso).order_by(Permiso.accion)).scalars().all()
    asignados = db.execute(
        select(RolPermiso).where(RolPermiso.rol_id == rol_id)
    ).scalars().all()

    asignados_set = {(rp.modulo_id, rp.permiso_id) for rp in asignados}

    return {
        "rol": {"id": rol.id, "nombre": rol.nombre},
        "modulos": [{"id": m.id, "codigo": m.codigo, "nombre": m.nombre} for m in modulos],
        "permisos": [{"id": p.id, "accion": p.accion} for p in permisos],
        "asignados": [{"modulo_id": m, "permiso_id": p} for m, p in asignados_set],
    }


@router.post("/roles/{rol_id}/permisos", response_class=JSONResponse)
async def asignar_permisos_rol(
    rol_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("seguridad", "editar")),
):
    """Asigna permisos a un rol (matriz RBAC)."""
    rol = db.get(Role, rol_id)
    if not rol:
        return JSONResponse(status_code=404, content={"error": "Rol no encontrado"})

    payload = await request.json()
    permisos = payload.get("permisos", [])  # Lista de {modulo_id, permiso_id}

    # Eliminar permisos existentes del rol
    db.execute(RolPermiso.__table__.delete().where(RolPermiso.rol_id == rol_id))

    # Insertar nuevos permisos
    for item in permisos:
        modulo_id = item.get("modulo_id")
        permiso_id = item.get("permiso_id")
        if modulo_id and permiso_id:
            db.add(RolPermiso(rol_id=rol_id, modulo_id=modulo_id, permiso_id=permiso_id))

    db.commit()
    return JSONResponse(status_code=200, content={"ok": True})

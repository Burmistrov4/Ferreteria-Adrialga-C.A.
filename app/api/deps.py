"""
Dependencias de Autenticación y Autorización para FastAPI.

Proporciona:
- get_current_user: extrae la sesión desde cookie HTTPOnly o Bearer token,
  verifica validez en sesiones_usuario / DB y retorna el Usuario activo.
- require_permission(modulo, accion): decorador/dependencia de autorización
  que valida roles y permisos según el RBAC.
"""

from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.database import get_db
from app.models import Modulo, Permiso, RolPermiso, SesionUsuario, Usuario

# Bearer token para encabezado Authorization
bearer_scheme = HTTPBearer(auto_error=False)

# Nombre de la cookie HTTPOnly donde se guarda el token de sesión
SESSION_COOKIE_NAME = "adrialga_session"


def _get_token_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[str]:
    """Extrae el token de la cookie HTTPOnly o del encabezado Bearer."""
    # 1. Intentar desde la cookie HTTPOnly
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        return token

    # 2. Intentar desde el encabezado Authorization: Bearer <token>
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials

    return None


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    """
    Dependencia que autentica al usuario actual.

    Extrae el token de la cookie HTTPOnly o del encabezado Bearer,
    valida el JWT, verifica la sesión activa en la BD y retorna el Usuario.

    Raises:
        HTTPException 401: si no hay token, es inválido, la sesión no existe
                           o está inactiva, o el usuario está inactivo.
    """
    token = _get_token_from_request(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado: falta token de sesión",
        )

    # Decodificar JWT
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )

    # Extraer subject (usuario_id)
    subject = payload.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sin subject",
        )

    try:
        usuario_id = int(subject)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Subject de token inválido",
        )

    # Verificar sesión activa en la BD
    sesion = db.scalar(
        select(SesionUsuario).where(
            SesionUsuario.id == token,
            SesionUsuario.usuario_id == usuario_id,
            SesionUsuario.activa.is_(True),
        )
    )
    if not sesion:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no válida o inactiva",
        )

    # Cargar usuario
    usuario = db.get(Usuario, usuario_id)
    if not usuario or not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo o no encontrado",
        )

    return usuario


def require_permission(modulo_codigo: str, accion: str) -> Callable:
    """
    Fábrica de dependencias de autorización RBAC.

    Valida que el usuario autenticado tenga el permiso `accion`
    sobre el módulo `modulo_codigo`.

    Args:
        modulo_codigo: Código del módulo (ej. 'pos', 'inventario', 'fiscal').
        accion: Acción requerida (ej. 'lectura', 'escritura', 'eliminacion').

    Returns:
        Dependencia FastAPI que valida el permiso.

    Uso:
        @app.get("/pos/facturas")
        def listar_facturas(
            usuario: Usuario = Depends(require_permission("pos", "lectura")),
        ):
            ...
    """

    def dependency(
        usuario: Usuario = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Usuario:
        # Superusuario tiene acceso total
        if usuario.es_superuser:
            return usuario

        # Buscar módulo y permiso
        modulo = db.scalar(select(Modulo).where(Modulo.codigo == modulo_codigo))
        permiso = db.scalar(select(Permiso).where(Permiso.accion == accion))

        if not modulo or not permiso:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Módulo '{modulo_codigo}' o permiso '{accion}' no configurado",
            )

        # Verificar rol_permisos
        tiene_permiso = db.scalar(
            select(RolPermiso).where(
                RolPermiso.rol_id == usuario.rol_id,
                RolPermiso.modulo_id == modulo.id,
                RolPermiso.permiso_id == permiso.id,
            )
        )

        if not tiene_permiso:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Usuario sin permiso '{accion}' en módulo '{modulo_codigo}'",
            )

        return usuario

    return dependency
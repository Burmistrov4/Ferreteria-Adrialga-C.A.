"""
Módulo de Seguridad — Hashing de contraseñas y tokens JWT.

Proporciona:
- Hashing de contraseñas con bcrypt (directo, sin passlib)
- Verificación de contraseñas
- Generación y validación de tokens JWT para cookies HTTPOnly
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt

# ---------------------------------------------------------------------------
# Hashing de contraseñas (bcrypt directo)
# ---------------------------------------------------------------------------


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña en texto plano contra su hash bcrypt almacenado."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    """Genera el hash bcrypt de una contraseña en texto plano."""
    # bcrypt limita a 72 bytes; truncar para evitar errores
    password_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


# ---------------------------------------------------------------------------
# Configuración de tokens JWT
# ---------------------------------------------------------------------------
# En producción, estas variables deben venir de variables de entorno.
SECRET_KEY = "adrialga-secret-key-cambiar-en-produccion"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 horas (turno laboral)


def create_access_token(
    subject: str | Any,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict] = None,
) -> str:
    """
    Genera un token JWT firmado.

    Args:
        subject: Identificador del sujeto (usuario_id o username).
        expires_delta: Tiempo de expiración personalizado.
        extra_claims: Reclamaciones adicionales (ej. rol, es_superuser).

    Returns:
        Token JWT codificado como string.
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode: dict[str, Any] = {"sub": str(subject), "exp": expire}
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    """
    Valida y decodifica un token JWT.

    Args:
        token: Token JWT a validar.

    Returns:
        Payload del token si es válido, None si es inválido o expiró.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
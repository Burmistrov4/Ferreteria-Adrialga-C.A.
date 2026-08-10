"""
Configuración centralizada de la aplicación — Ferretería Adrialga C.A. ERP/POS.
"""
import os
import warnings
from pathlib import Path

# Rutas base
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Seguridad y JWT
SECRET_KEY: str = os.getenv("SECRET_KEY", "9a82647db0916ff46817293a38b1f582f3c0db692b1b3b1f574d7883db61a7a0")
ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

# Base de Datos (Adaptación automática para Render/PostgreSQL)
raw_db_url = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'adrialga.db'}")
if raw_db_url.startswith("postgres://"):
    DATABASE_URL = raw_db_url.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = raw_db_url

# Servidor y Entorno
DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))
RENDER_EXTERNAL_URL: str = os.getenv("RENDER_EXTERNAL_URL", "")

# Validaciones en producción
if not DEBUG and SECRET_KEY == "9a82647db0916ff46817293a38b1f582f3c0db692b1b3b1f574d7883db61a7a0":
    warnings.warn("SECRET_KEY no fue modificada desde el valor por defecto. Cambiar en producción.")

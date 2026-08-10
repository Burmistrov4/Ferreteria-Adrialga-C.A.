"""
Configuración de la base de datos para el sistema ERP/POS de Ferretería Adrialga, C.A.

Proporciona:
- Motor de conexión SQLAlchemy (create_engine)
- Fábrica de sesiones (sessionmaker)
- Clase base declarativa global (Base)
- Dependencia generadora de sesión para FastAPI (get_db)
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ---------------------------------------------------------------------------
# Configuración de conexión
# ---------------------------------------------------------------------------
# Por defecto usa SQLite para desarrollo local. Para producción con PostgreSQL
# cambiar la URL, por ejemplo:
#   DATABASE_URL = "postgresql+psycopg://usuario:clave@localhost:5432/adrialga"
DATABASE_URL = "sqlite:///./adrialga.db"

# `check_same_thread=False` es necesario para SQLite con FastAPI (múltiples hilos)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Clase base declarativa global para todos los modelos ORM."""


def get_db() -> Generator[Session, None, None]:
    """
    Dependencia de FastAPI que provee una sesión de base de datos por request.

    Uso:
        @app.get("/productos")
        def listar_productos(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
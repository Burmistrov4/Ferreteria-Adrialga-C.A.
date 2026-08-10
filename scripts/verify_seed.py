"""Script de verificación del seed — Ferretería Adrialga, C.A."""

from sqlalchemy import select

from app.core.security import verify_password
from app.db.database import SessionLocal
from app.models import ConfiguracionFiscal, FormaPago, Role, RolPermiso, Usuario


def main() -> None:
    db = SessionLocal()
    try:
        admin = db.scalar(select(Usuario).where(Usuario.username == "admin"))
        print(f"Admin: {admin.username} | superuser: {admin.es_superuser} | activo: {admin.activo}")
        print(f"Password OK: {verify_password('Admin1234*', admin.password_hash)}")

        alicuotas = db.scalars(select(ConfiguracionFiscal)).all()
        print(f"Alicuotas SENIAT: {len(alicuotas)} -> {[(a.codigo, float(a.porcentaje)) for a in alicuotas]}")

        formas_pago = db.scalars(select(FormaPago)).all()
        print(f"Formas de pago: {len(formas_pago)}")

        roles = db.scalars(select(Role)).all()
        print(f"Roles: {len(roles)}")

        rol_permisos = db.scalars(select(RolPermiso)).all()
        print(f"Mapeos Rol-Permisos: {len(rol_permisos)}")

        print("VERIFICACION COMPLETA OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
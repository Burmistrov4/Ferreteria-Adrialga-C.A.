"""
Script de Poblamiento de Datos Maestros (Data Seeding) — Ferretería Adrialga, C.A.

Ejecución:
    python -m scripts.seed_data

Idempotente: comprueba si los datos existen antes de insertarlos.
Puebla: configuracion_fiscal, roles, modulos, permisos, rol_permisos,
        usuario admin, formas_pago, correlativos_fiscales, tasas_ref.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.database import Base, SessionLocal, engine
from app.models import (
    ConfiguracionFiscal,
    CorrelativoFiscal,
    FormaPago,
    Modulo,
    Permiso,
    Role,
    RolPermiso,
    TasaRef,
    Usuario,
)


# ---------------------------------------------------------------------------
# Datos maestros a insertar
# ---------------------------------------------------------------------------

ALICUOTAS_SENIAT = [
    {"codigo": "G", "porcentaje": Decimal("16.00"), "descripcion": "General"},
    {"codigo": "R", "porcentaje": Decimal("8.00"), "descripcion": "Reducida"},
    {"codigo": "A", "porcentaje": Decimal("31.00"), "descripcion": "Suntuaria/Adicional"},
    {"codigo": "E", "porcentaje": Decimal("0.00"), "descripcion": "Exento"},
]

ROLES = [
    {"nombre": "Superusuario", "descripcion": "Acceso total al sistema"},
    {"nombre": "Administrador", "descripcion": "Gestión administrativa completa"},
    {"nombre": "Cajero", "descripcion": "Operaciones de punto de venta"},
    {"nombre": "Inventariante", "descripcion": "Gestión de inventario y almacén"},
]

MODULOS = [
    {"codigo": "pos", "nombre": "Punto de Venta"},
    {"codigo": "inventario", "nombre": "Inventario y Almacén"},
    {"codigo": "compras", "nombre": "Compras y Proveedores"},
    {"codigo": "cxc_cxp", "nombre": "Cuentas por Cobrar / Pagar"},
    {"codigo": "fiscal", "nombre": "Módulo Fiscal SENIAT"},
    {"codigo": "seguridad", "nombre": "Seguridad y Usuarios"},
]

PERMISOS = [
    {"accion": "lectura"},
    {"accion": "escritura"},
    {"accion": "eliminacion"},
    {"accion": "autorizacion_descuento"},
]

# Roles con acceso total (Superusuario y Administrador)
ROLES_ACCESO_TOTAL = ["Superusuario", "Administrador"]

ADMIN_USER = {
    "username": "admin",
    "email": "admin@ferreteriaadrialga.com",
    "password": "Admin1234*",
    "nombre_completo": "Administrador del Sistema",
}

FORMAS_PAGO = [
    {"codigo": "EFECTIVO_BS", "nombre": "Efectivo Bolívares", "requiere_referencia": False},
    {"codigo": "PAGO_MOVIL", "nombre": "Pago Móvil", "requiere_referencia": True},
    {"codigo": "PUNTO_VENTA", "nombre": "Punto de Venta / Débito", "requiere_referencia": True},
    {"codigo": "TRANSFERENCIA", "nombre": "Transferencia Bancaria", "requiere_referencia": True},
    {"codigo": "EFECTIVO_USD", "nombre": "Efectivo Divisa USD", "requiere_referencia": False},
    {"codigo": "ZELLE", "nombre": "Zelle USD", "requiere_referencia": True},
]

CORRELATIVOS = [
    {"tipo_documento": "FACTURA", "serie": "A", "ultimo_numero": 0},
]

TASA_REF_INICIAL = {
    "monto_bs": Decimal("742.8100"),
    "origen": "BCV",
}


# ---------------------------------------------------------------------------
# Funciones de seeding (idempotentes)
# ---------------------------------------------------------------------------

def seed_configuracion_fiscal(db: Session) -> None:
    """Inserta las alícuotas SENIAT si no existen."""
    for item in ALICUOTAS_SENIAT:
        exists = db.scalar(
            select(ConfiguracionFiscal).where(
                ConfiguracionFiscal.codigo == item["codigo"]
            )
        )
        if not exists:
            db.add(ConfiguracionFiscal(**item))
            print(f"  + Alícuota {item['codigo']} ({item['porcentaje']}%) insertada")
        else:
            print(f"  = Alícuota {item['codigo']} ya existe")


def seed_roles(db: Session) -> None:
    """Inserta los roles RBAC si no existen."""
    for item in ROLES:
        exists = db.scalar(select(Role).where(Role.nombre == item["nombre"]))
        if not exists:
            db.add(Role(**item))
            print(f"  + Rol '{item['nombre']}' insertado")
        else:
            print(f"  = Rol '{item['nombre']}' ya existe")
    db.flush()  # Persistir roles para que estén disponibles en consultas posteriores


def seed_modulos(db: Session) -> None:
    """Inserta los módulos del sistema si no existen."""
    for item in MODULOS:
        exists = db.scalar(select(Modulo).where(Modulo.codigo == item["codigo"]))
        if not exists:
            db.add(Modulo(**item))
            print(f"  + Módulo '{item['codigo']}' insertado")
        else:
            print(f"  = Módulo '{item['codigo']}' ya existe")
    db.flush()  # Persistir módulos para que estén disponibles en consultas posteriores


def seed_permisos(db: Session) -> None:
    """Inserta los permisos si no existen."""
    for item in PERMISOS:
        exists = db.scalar(select(Permiso).where(Permiso.accion == item["accion"]))
        if not exists:
            db.add(Permiso(**item))
            print(f"  + Permiso '{item['accion']}' insertado")
        else:
            print(f"  = Permiso '{item['accion']}' ya existe")
    db.flush()  # Persistir permisos para que estén disponibles en consultas posteriores


def seed_rol_permisos(db: Session) -> None:
    """Mapea Superusuario y Administrador con acceso total a todos los módulos y permisos."""
    roles = {r.nombre: r for r in db.scalars(select(Role)).all()}
    modulos = {m.codigo: m for m in db.scalars(select(Modulo)).all()}
    permisos = {p.accion: p for p in db.scalars(select(Permiso)).all()}

    for rol_nombre in ROLES_ACCESO_TOTAL:
        rol = roles.get(rol_nombre)
        if not rol:
            continue
        for modulo in modulos.values():
            for permiso in permisos.values():
                exists = db.scalar(
                    select(RolPermiso).where(
                        RolPermiso.rol_id == rol.id,
                        RolPermiso.modulo_id == modulo.id,
                        RolPermiso.permiso_id == permiso.id,
                    )
                )
                if not exists:
                    db.add(
                        RolPermiso(
                            rol_id=rol.id,
                            modulo_id=modulo.id,
                            permiso_id=permiso.id,
                        )
                    )
    db.flush()  # Persistir mapeos RBAC
    print(f"  + Permisos RBAC mapeados para roles: {', '.join(ROLES_ACCESO_TOTAL)}")


def seed_admin_user(db: Session) -> None:
    """Inserta el usuario administrador inicial si no existe."""
    exists = db.scalar(
        select(Usuario).where(Usuario.username == ADMIN_USER["username"])
    )
    if exists:
        print(f"  = Usuario '{ADMIN_USER['username']}' ya existe")
        return

    rol_super = db.scalar(select(Role).where(Role.nombre == "Superusuario"))
    if not rol_super:
        print("  ! ERROR: Rol 'Superusuario' no encontrado. Ejecuta seed_roles primero.")
        return

    db.add(
        Usuario(
            nombre_completo=ADMIN_USER["nombre_completo"],
            username=ADMIN_USER["username"],
            email=ADMIN_USER["email"],
            password_hash=get_password_hash(ADMIN_USER["password"]),
            rol_id=rol_super.id,
            activo=True,
            es_superuser=True,
        )
    )
    print(f"  + Usuario admin '{ADMIN_USER['username']}' insertado")


def seed_formas_pago(db: Session) -> None:
    """Inserta las formas de pago por defecto si no existen."""
    for item in FORMAS_PAGO:
        exists = db.scalar(select(FormaPago).where(FormaPago.codigo == item["codigo"]))
        if not exists:
            db.add(FormaPago(**item))
            print(f"  + Forma de pago '{item['codigo']}' insertada")
        else:
            print(f"  = Forma de pago '{item['codigo']}' ya existe")


def seed_correlativos(db: Session) -> None:
    """Inserta los correlativos fiscales iniciales si no existen."""
    for item in CORRELATIVOS:
        exists = db.scalar(
            select(CorrelativoFiscal).where(
                CorrelativoFiscal.tipo_documento == item["tipo_documento"],
                CorrelativoFiscal.serie == item["serie"],
            )
        )
        if not exists:
            db.add(CorrelativoFiscal(**item))
            print(f"  + Correlativo {item['tipo_documento']} serie {item['serie']} insertado")
        else:
            print(f"  = Correlativo {item['tipo_documento']} serie {item['serie']} ya existe")


def seed_tasa_ref(db: Session) -> None:
    """Inserta una tasa REF inicial del BCV si no existe ninguna."""
    count = db.scalar(select(TasaRef).limit(1))
    if count is None:
        db.add(
            TasaRef(
                fecha=datetime.now(timezone.utc),
                monto_bs=TASA_REF_INICIAL["monto_bs"],
                origen=TASA_REF_INICIAL["origen"],
            )
        )
        print(f"  + Tasa REF inicial {TASA_REF_INICIAL['monto_bs']} Bs/REF insertada")
    else:
        print("  = Ya existe al menos una tasa REF")


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------

def run_seed() -> None:
    """Crea las tablas y ejecuta todos los seeds en orden."""
    print("=== Creando tablas (si no existen) ===")
    Base.metadata.create_all(bind=engine)
    print("=== Tablas listas ===")

    db = SessionLocal()
    try:
        print("\n--- Configuración Fiscal SENIAT ---")
        seed_configuracion_fiscal(db)

        print("\n--- Roles RBAC ---")
        seed_roles(db)

        print("\n--- Módulos ---")
        seed_modulos(db)

        print("\n--- Permisos ---")
        seed_permisos(db)

        print("\n--- Mapeo Rol-Permisos (acceso total) ---")
        seed_rol_permisos(db)

        print("\n--- Usuario Administrador ---")
        seed_admin_user(db)

        print("\n--- Formas de Pago ---")
        seed_formas_pago(db)

        print("\n--- Correlativos Fiscales ---")
        seed_correlativos(db)

        print("\n--- Tasa REF Inicial ---")
        seed_tasa_ref(db)

        db.commit()
        print("\n=== SEED COMPLETADO EXITOSAMENTE ===")
    except Exception as e:
        db.rollback()
        print(f"\n=== ERROR DURANTE EL SEED: {e} ===")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
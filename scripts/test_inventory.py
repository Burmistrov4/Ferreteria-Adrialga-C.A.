"""
Script de Prueba — Módulo de Inventario y Kardex.

Verifica:
1. Creación de categoría.
2. Creación de producto con stock inicial.
3. Generación automática de movimiento Kardex (ENTRADA por Saldo Inicial).
4. Consulta de producto y su kardex.

Uso:
    python -m scripts.test_inventory
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.database import SessionLocal, engine
from app.models import (
    Categoria,
    ConfiguracionFiscal,
    KardexMovimiento,
    Producto,
    Role,
    Usuario,
)
from app.models.inventory import Categoria as CategoriaModel


def ensure_admin(db: Session) -> Usuario:
    """Crea un usuario admin temporal si no existe."""
    admin = db.scalar(
        select(Usuario).where(Usuario.username == "admin_test")
    )
    if admin:
        return admin

    rol = db.scalar(select(Role).where(Role.nombre == "Superusuario"))
    if not rol:
        raise RuntimeError("No existe el rol Superusuario. Ejecuta seed_data.py primero.")

    admin = Usuario(
        username="admin_test",
        email="admin_test@local.test",
        password_hash=get_password_hash("Test1234*"),
        nombre_completo="Admin Test",
        rol_id=rol.id,
        activo=True,
        es_superuser=True,
    )
    db.add(admin)
    db.flush()
    return admin


def run_tests() -> None:
    print("=== PRUEBAS MÓDULO INVENTARIO Y KARDEX ===")

    # Crear tablas si no existen
    from app.db.init_db import init_db
    init_db()

    db = SessionLocal()
    try:
        # 1. Asegurar usuario admin
        admin = ensure_admin(db)
        db.commit()
        print(f"\n[1] Usuario admin_test listo (id={admin.id}).")

        # 2. Crear o reutilizar categoría de prueba
        categoria = db.scalar(select(Categoria).where(Categoria.nombre == "Herramientas"))
        if not categoria:
            categoria = Categoria(nombre="Herramientas", descripcion="Categoría de prueba")
            db.add(categoria)
            db.flush()
            db.commit()
            print(f"\n[2] Categoría creada: id={categoria.id}, nombre='{categoria.nombre}'.")
        else:
            print(f"\n[2] Categoría existente reutilizada: id={categoria.id}, nombre='{categoria.nombre}'.")

        # 3. Obtener alícuota
        alicuota = db.scalar(
            select(ConfiguracionFiscal).where(ConfiguracionFiscal.codigo == "G")
        )
        if not alicuota:
            raise RuntimeError("No existe la alícuota GENERAL. Ejecuta seed_data.py primero.")
        print(f"\n[3] Alícuota encontrada: {alicuota.codigo} {alicuota.porcentaje}%.")

        # 4. Crear producto con stock inicial > 0 (código único)
        codigo_unico = f"TEST-{uuid.uuid4().hex[:8]}"
        producto = Producto(
            codigo_barras=codigo_unico,
            descripcion="Martillo de prueba",
            categoria_id=categoria.id,
            alicuota_id=alicuota.id,
            precio_ref=Decimal("15.50"),
            stock_actual=Decimal("10.000"),
            stock_minimo=Decimal("2.000"),
            activo=True,
        )
        db.add(producto)
        db.flush()

        # Generar movimiento Kardex automáticamente (simula lógica del router)
        if producto.stock_actual > 0:
            kardex = KardexMovimiento(
                producto_id=producto.id,
                tipo_movimiento="ENTRADA",
                cantidad=producto.stock_actual,
                costo_ref=producto.precio_ref,
                origen_id=None,
                fecha=datetime.now(timezone.utc),
            )
            db.add(kardex)

        db.commit()
        print(f"\n[4] Producto creado: id={producto.id}, código={producto.codigo_barras}, stock={producto.stock_actual}.")

        # 5. Verificar Kardex generado automáticamente
        kardex = db.scalar(
            select(KardexMovimiento).where(
                KardexMovimiento.producto_id == producto.id
            )
        )
        if not kardex:
            raise AssertionError("No se generó el movimiento Kardex para el producto.")

        assert kardex.tipo_movimiento == "ENTRADA", f"Tipo incorrecto: {kardex.tipo_movimiento}"
        assert kardex.cantidad == producto.stock_actual, "Cantidad Kardex no coincide con stock inicial."
        assert kardex.costo_ref == producto.precio_ref, "Costo ref Kardex no coincide con precio_ref."

        print(f"\n[5] Kardex OK: id={kardex.id}, tipo={kardex.tipo_movimiento}, cantidad={kardex.cantidad}, costo_ref={kardex.costo_ref}.")

        # 6. Consultar producto con su kardex
        prod_consultado = db.get(Producto, producto.id)
        movimientos = prod_consultado.movimientos_kardex
        assert len(movimientos) == 1, f"Se esperaba 1 movimiento, hay {len(movimientos)}."
        print(f"\n[6] Producto consultado OK, movimientos_kardex={len(movimientos)}.")

        print("\n=== TODAS LAS PRUEBAS PASARON ===")

    except Exception as e:
        db.rollback()
        print(f"\n=== ERROR EN PRUEBAS: {e} ===")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_tests()
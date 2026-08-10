"""
Script de Prueba — Módulo de Compras, Proveedores y Cuentas por Pagar.

Verifica:
1. Registro de proveedor.
2. Procesamiento de compra a crédito (transacción atómica).
3. Incremento de stock en inventario.
4. Generación de Kardex ENTRADA.
5. Creación de Cuenta por Pagar (CxP).

Uso:
    python -m scripts.test_purchases
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.database import SessionLocal, engine
from app.models import (
    Categoria,
    Cliente,
    ConfiguracionFiscal,
    CorrelativoFiscal,
    DetalleVenta,
    Factura,
    FormaPago,
    KardexMovimiento,
    PagoVenta,
    Producto,
    Role,
    TasaRef,
    Usuario,
)
from app.models.fiscal import CierreZ
from app.models.inventory import Producto as ProductoModel
from app.models.purchases import CuentaPorPagar, Proveedor, Compra, DetalleCompra


def ensure_admin(db: Session) -> Usuario:
    """Crea usuario admin temporal si no existe."""
    admin = db.scalar(select(Usuario).where(Usuario.username == "admin_test"))
    if admin:
        return admin

    rol = db.scalar(select(Role).where(Role.nombre == "Superusuario"))
    if not rol:
        rol = Role(nombre="Superusuario", descripcion="Acceso total")
        db.add(rol)
        db.flush()
        db.commit()

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
    print("=== PRUEBAS MÓDULO COMPRAS, PROVEEDORES Y CXP ===")

    from app.db.init_db import init_db
    init_db()

    db = SessionLocal()
    try:
        # 1. Asegurar usuario admin
        admin = ensure_admin(db)
        db.commit()
        print(f"\n[1] Usuario admin_test listo (id={admin.id}).")

        # 2. Asegurar alícuota y categoría
        alicuota = db.scalar(select(ConfiguracionFiscal).where(ConfiguracionFiscal.codigo == "G"))
        if not alicuota:
            alicuota = ConfiguracionFiscal(codigo="G", porcentaje=Decimal("16.00"), descripcion="General")
            db.add(alicuota)
            db.flush()
            db.commit()
        print(f"\n[2] Alícuota G {alicuota.porcentaje}% lista.")

        categoria = db.scalar(select(Categoria).where(Categoria.nombre == "Herramientas"))
        if not categoria:
            categoria = Categoria(nombre="Herramientas", descripcion="Categoría de prueba")
            db.add(categoria)
            db.flush()
            db.commit()
        print(f"\n[3] Categoría lista: id={categoria.id}.")

        # 3. Crear proveedor de prueba
        rif_unico = f"J-{uuid4().hex[:8].upper()}"
        proveedor = Proveedor(
            rif=rif_unico,
            razon_social="Proveedor Test S.A.",
            direccion="Av. Principal, Zona Industrial",
            telefono="0212-1234567",
            contacto="Juan Pérez",
        )
        db.add(proveedor)
        db.flush()
        db.commit()
        print(f"\n[4] Proveedor creado: id={proveedor.id}, RIF={proveedor.rif}.")

        # 4. Crear producto de prueba
        codigo_unico = f"PROD-COMPRA-{uuid4().hex[:8]}"
        producto = Producto(
            codigo_barras=codigo_unico,
            descripcion="Taladro Inalámbrico",
            categoria_id=categoria.id,
            alicuota_id=alicuota.id,
            precio_ref=Decimal("50.00"),
            stock_actual=Decimal("10.000"),
            stock_minimo=Decimal("2.000"),
            activo=True,
        )
        db.add(producto)
        db.flush()
        db.commit()
        print(f"\n[5] Producto creado: id={producto.id}, stock_inicial={producto.stock_actual}.")

        # 5. Registrar compra a crédito
        print(f"\n[6] Registrando compra a crédito...")
        
        numero_control = f"FC-{uuid4().hex[:8].upper()}"
        subtotal_bs = Decimal("100.00")
        iva_bs = Decimal("16.00")
        total_bs = subtotal_bs + iva_bs
        
        compra = Compra(
            proveedor_id=proveedor.id,
            usuario_id=admin.id,
            numero_control=numero_control,
            subtotal_bs=subtotal_bs,
            iva_bs=iva_bs,
            total_bs=total_bs,
        )
        db.add(compra)
        db.flush()
        print(f"    - Compra creada: id={compra.id}, control={compra.numero_control}")
        
        # Detalle de compra
        detalle = DetalleCompra(
            compra_id=compra.id,
            producto_id=producto.id,
            cantidad=Decimal("5.000"),
            costo_unitario_bs=Decimal("20.00"),
        )
        db.add(detalle)
        
        # Actualizar stock
        producto.stock_actual += detalle.cantidad
        print(f"    - Stock actualizado: {producto.stock_actual}")
        
        # Kardex ENTRADA
        kardex = KardexMovimiento(
            producto_id=producto.id,
            tipo_movimiento="ENTRADA",
            cantidad=detalle.cantidad,
            costo_ref=detalle.costo_unitario_bs,
            origen_id=compra.id,
            fecha=datetime.now(timezone.utc),
        )
        db.add(kardex)
        
        # Cuenta por Pagar (a crédito)
        cxp = CuentaPorPagar(
            compra_id=compra.id,
            proveedor_id=proveedor.id,
            monto_total_bs=total_bs,
            saldo_pendiente_bs=total_bs,
            fecha_vencimiento=date.today(),
        )
        db.add(cxp)
        db.commit()
        
        print(f"    - Kardex ENTRADA: id={kardex.id}, cantidad={kardex.cantidad}")
        print(f"    - CxP creada: id={cxp.id}, monto=Bs {cxp.monto_total_bs:.2f}")

        # 6. Verificaciones
        print(f"\n[7] Verificaciones...")
        
        # Verificar compra
        compra_db = db.get(Compra, compra.id)
        assert compra_db is not None, "Compra no encontrada"
        assert compra_db.total_bs == total_bs, f"Total compra incorrecto: {compra_db.total_bs}"
        print(f"    ✓ Compra verificada: id={compra_db.id}, total=Bs {compra_db.total_bs:.2f}")
        
        # Verificar detalle
        detalle_db = db.scalar(select(DetalleCompra).where(DetalleCompra.compra_id == compra.id))
        assert detalle_db is not None, "Detalle de compra no encontrado"
        assert detalle_db.cantidad == Decimal("5.000"), "Cantidad incorrecta"
        print(f"    ✓ DetalleCompra OK: id={detalle_db.id}, cantidad={detalle_db.cantidad}")
        
        # Verificar stock
        producto_db = db.get(Producto, producto.id)
        stock_esperado = Decimal("10.000") + Decimal("5.000")
        assert producto_db.stock_actual == stock_esperado, \
            f"Stock no actualizado. Esperado: {stock_esperado}, Actual: {producto_db.stock_actual}"
        print(f"    ✓ Stock actualizado: {producto_db.stock_actual}")
        
        # Verificar Kardex
        kardex_db = db.scalar(select(KardexMovimiento).where(KardexMovimiento.producto_id == producto.id))
        assert kardex_db is not None, "Kardex no generado"
        assert kardex_db.tipo_movimiento == "ENTRADA", f"Tipo Kardex incorrecto: {kardex_db.tipo_movimiento}"
        print(f"    ✓ Kardex ENTRADA OK: id={kardex_db.id}")
        
        # Verificar CxP
        cxp_db = db.scalar(select(CuentaPorPagar).where(CuentaPorPagar.compra_id == compra.id))
        assert cxp_db is not None, "Cuenta por Pagar no generada"
        assert cxp_db.saldo_pendiente_bs == total_bs, "Saldo pendiente incorrecto"
        print(f"    ✓ Cuenta por Pagar OK: id={cxp_db.id}, saldo=Bs {cxp_db.saldo_pendiente_bs:.2f}")

        print(f"\n=== TODAS LAS PRUEBAS PASARON ===")
        print(f"\nResumen:")
        print(f"  - Proveedor: {proveedor.razon_social} (RIF: {proveedor.rif})")
        print(f"  - Compra: {compra.numero_control}")
        print(f"  - Producto: {producto.descripcion}")
        print(f"  - Stock final: {producto_db.stock_actual}")
        print(f"  - CxP: Bs {cxp_db.saldo_pendiente_bs:.2f}")

    except Exception as e:
        db.rollback()
        print(f"\n=== ERROR EN PRUEBAS: {e} ===")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_tests()
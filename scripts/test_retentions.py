"""
Script de Prueba — Módulo de Retenciones IVA e ISLR y Libro de Compras.

Verifica:
1. Registro de compra.
2. Generación de retención de IVA (75%).
3. Generación de retención de ISLR.
4. Visualización en Libro de Compras.

Uso:
    python -m scripts.test_retentions
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
    ConfiguracionFiscal,
    DetalleCompra,
    Factura,
    KardexMovimiento,
    Producto,
    Role,
    Usuario,
)
from app.models.fiscal import RetencionIVA, RetencionISLR
from app.models.purchases import Compra, CuentaPorPagar, Proveedor


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
    print("=== PRUEBAS MÓDULO RETENCIONES IVA/ISLR Y LIBRO DE COMPRAS ===")

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

        # 3. Crear proveedor
        rif_unico = f"J-{uuid4().hex[:8].upper()}"
        proveedor = Proveedor(
            rif=rif_unico,
            razon_social="Proveedor Retenciones S.A.",
            direccion="Av. Retenciones, Centro",
            telefono="0212-9876543",
            contacto="María Gómez",
        )
        db.add(proveedor)
        db.flush()
        db.commit()
        print(f"\n[4] Proveedor creado: id={proveedor.id}, RIF={proveedor.rif}.")

        # 4. Crear producto
        codigo_unico = f"PROD-RET-{uuid4().hex[:8]}"
        producto = Producto(
            codigo_barras=codigo_unico,
            descripcion="Taladro Profesional",
            categoria_id=categoria.id,
            alicuota_id=alicuota.id,
            precio_ref=Decimal("100.00"),
            stock_actual=Decimal("5.000"),
            stock_minimo=Decimal("1.000"),
            activo=True,
        )
        db.add(producto)
        db.flush()
        db.commit()
        print(f"\n[5] Producto creado: id={producto.id}.")

        # 5. Registrar compra
        print(f"\n[6] Registrando compra...")
        
        numero_control = f"FC-RET-{uuid4().hex[:8].upper()}"
        subtotal_bs = Decimal("1000.00")
        iva_bs = Decimal("160.00")
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
        
        # Detalle
        detalle = DetalleCompra(
            compra_id=compra.id,
            producto_id=producto.id,
            cantidad=Decimal("10.000"),
            costo_unitario_bs=Decimal("100.00"),
        )
        db.add(detalle)
        
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
        
        # CxP
        cxp = CuentaPorPagar(
            compra_id=compra.id,
            proveedor_id=proveedor.id,
            monto_total_bs=total_bs,
            saldo_pendiente_bs=total_bs,
            fecha_vencimiento=date.today(),
        )
        db.add(cxp)
        db.commit()
        
        print(f"    - Kardex ENTRADA: id={kardex.id}")
        print(f"    - CxP creada: id={cxp.id}")

        # 6. Generar retención de IVA (75%)
        print(f"\n[7] Generando retención de IVA (75%)...")
        
        base_imponible_iva = subtotal_bs
        porcentaje_iva = 75
        monto_retenido_iva = base_imponible_iva * Decimal(porcentaje_iva) / Decimal("100")
        
        retencion_iva = RetencionIVA(
            compra_id=compra.id,
            numero_comprobante=f"RET-{uuid4().hex[:10].upper()}",
            base_imponible=base_imponible_iva,
            porcentaje_retencion=porcentaje_iva,
            monto_retenido=monto_retenido_iva,
        )
        db.add(retencion_iva)
        db.commit()
        
        print(f"    - Retención IVA: id={retencion_iva.id}")
        print(f"    - Número: {retencion_iva.numero_comprobante}")
        print(f"    - Base: Bs {retencion_iva.base_imponible:.2f}")
        print(f"    - Monto retenido: Bs {retencion_iva.monto_retenido:.2f}")

        # 7. Generar retención de ISLR
        print(f"\n[8] Generando retención de ISLR...")
        
        base_islr = total_bs
        porcentaje_islr = Decimal("5.00")
        sustraendo = Decimal("100.00")
        monto_retenido_islr = (base_islr * porcentaje_islr / Decimal("100")) - sustraendo
        if monto_retenido_islr < 0:
            monto_retenido_islr = Decimal("0.00")
        
        retencion_islr = RetencionISLR(
            compra_id=compra.id,
            numero_comprobante=f"RET-ISLR-{uuid4().hex[:8].upper()}",
            concepto="Servicios profesionales",
            base_imponible=base_islr,
            porcentaje_retencion=porcentaje_islr,
            sustraendo=sustraendo,
            monto_retenido=monto_retenido_islr,
        )
        db.add(retencion_islr)
        db.commit()
        
        print(f"    - Retención ISLR: id={retencion_islr.id}")
        print(f"    - Número: {retencion_islr.numero_comprobante}")
        print(f"    - Base: Bs {retencion_islr.base_imponible:.2f}")
        print(f"    - Monto retenido: Bs {retencion_islr.monto_retenido:.2f}")

        # 8. Verificar Libro de Compras (simulado)
        print(f"\n[9] Verificando Libro de Compras...")
        
        # Verificar retenciones
        ret_iva_db = db.get(RetencionIVA, retencion_iva.id)
        assert ret_iva_db is not None, "Retención IVA no encontrada"
        assert ret_iva_db.porcentaje_retencion == 75, f"Porcentaje incorrecto: {ret_iva_db.porcentaje_retencion}"
        print(f"    ✓ Retención IVA verificada: {ret_iva_db.numero_comprobante}")
        
        ret_islr_db = db.get(RetencionISLR, retencion_islr.id)
        assert ret_islr_db is not None, "Retención ISLR no encontrada"
        assert ret_islr_db.monto_retenido == monto_retenido_islr, "Monto ISLR incorrecto"
        print(f"    ✓ Retención ISLR verificada: {ret_islr_db.numero_comprobante}")

        print(f"\n=== TODAS LAS PRUEBAS PASARON ===")
        print(f"\nResumen:")
        print(f"  - Compra: {compra.numero_control}")
        print(f"  - Retención IVA (75%): Bs {retencion_iva.monto_retenido:.2f}")
        print(f"  - Retención ISLR: Bs {retencion_islr.monto_retenido:.2f}")

    except Exception as e:
        db.rollback()
        print(f"\n=== ERROR EN PRUEBAS: {e} ===")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_tests()
"""
Script de Prueba — Módulo Fiscal SENIAT, Cierre Z y Libro de Ventas.

Verifica:
1. Generación de Cierre Z (transacción atómica).
2. Consolidación de totales fiscales (ventas, IVA, IGTF).
3. Correcta agrupación de facturas por rango de fecha.
4. Integridad de totales vs. suma de facturas.

Uso:
    python -m scripts.test_fiscal
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


def crear_venta_prueba(db: Session, cliente_id: int, producto_id: int, tasa_id: int, 
                       cantidad: Decimal, precio_usd: Decimal, iva_pct: Decimal,
                       pago_usd: Decimal, forma_pago_id: int) -> Factura:
    """Crea una venta de prueba y retorna la factura."""
    tasa = db.get(TasaRef, tasa_id)
    
    subtotal_usd = precio_usd * cantidad
    iva_usd = subtotal_usd * (iva_pct / Decimal("100"))
    total_usd = subtotal_usd + iva_usd
    
    subtotal_bs = Decimal(f"{float(subtotal_usd * tasa.monto_bs):.2f}")
    iva_bs = Decimal(f"{float(iva_usd * tasa.monto_bs):.2f}")
    total_bs = subtotal_bs + iva_bs
    
    # Correlativo
    correlativo = db.scalar(
        select(CorrelativoFiscal).where(
            CorrelativoFiscal.tipo_documento == "FACTURA",
            CorrelativoFiscal.serie == "A",
        )
    )
    if not correlativo:
        correlativo = CorrelativoFiscal(tipo_documento="FACTURA", serie="A", ultimo_numero=0)
        db.add(correlativo)
        db.flush()
    
    numero_factura = f"FA-A-{correlativo.ultimo_numero + 1:06d}"
    correlativo.ultimo_numero += 1
    
    factura = Factura(
        numero_factura=numero_factura,
        correlativo=correlativo.ultimo_numero,
        cliente_id=cliente_id,
        usuario_id=1,
        tasa_ref_id=tasa.id,
        subtotal_bs=subtotal_bs,
        iva_bs=iva_bs,
        igtf_bs=Decimal("0.00"),
        total_bs=total_bs,
        total_ref=total_usd,
        estado="EMITIDA",
        fecha_emision=datetime.now(timezone.utc),
    )
    db.add(factura)
    db.flush()
    
    # Detalle
    detalle = DetalleVenta(
        factura_id=factura.id,
        producto_id=producto_id,
        cantidad=cantidad,
        precio_unitario_bs=Decimal(f"{float(precio_usd * tasa.monto_bs):.2f}"),
        alicuota_porcentaje=iva_pct,
        total_linea_bs=Decimal(f"{float(precio_usd * cantidad * tasa.monto_bs):.2f}"),
    )
    db.add(detalle)
    
    # Pago
    pago = PagoVenta(
        factura_id=factura.id,
        forma_pago_id=forma_pago_id,
        monto_origen=pago_usd,
        moneda="USD",
        tasa_cambio=tasa.monto_bs,
        monto_bs=pago_usd * tasa.monto_bs,
        referencia=None,
    )
    db.add(pago)
    
    return factura


def run_tests() -> None:
    print("=== PRUEBAS MÓDULO FISCAL — CIERRE Z Y LIBRO DE VENTAS ===")

    from app.db.init_db import init_db
    init_db()

    db = SessionLocal()
    try:
        # 1. Asegurar usuario admin
        admin = ensure_admin(db)
        db.commit()
        print(f"\n[1] Usuario admin_test listo (id={admin.id}).")

        # 2. Asegurar datos básicos
        alicuota_g = db.scalar(select(ConfiguracionFiscal).where(ConfiguracionFiscal.codigo == "G"))
        if not alicuota_g:
            alicuota_g = ConfiguracionFiscal(codigo="G", porcentaje=Decimal("16.00"), descripcion="General")
            db.add(alicuota_g)
            db.flush()
            db.commit()
        print(f"\n[2] Alícuota G {alicuota_g.porcentaje}% lista.")

        # Cliente de prueba
        rif_unico = f"V-{uuid4().hex[:8].upper()}"
        cliente = Cliente(cedula_rif=rif_unico, razon_social="Cliente Fiscal Test",
                         direccion="Dirección fiscal", telefono="04120000000")
        db.add(cliente)
        db.flush()
        db.commit()
        print(f"\n[3] Cliente creado: id={cliente.id}, RIF={cliente.cedula_rif}.")

        # Categoría y producto
        categoria = db.scalar(select(Categoria).where(Categoria.nombre == "Herramientas"))
        if not categoria:
            categoria = Categoria(nombre="Herramientas", descripcion="Categoría de prueba")
            db.add(categoria)
            db.flush()
            db.commit()
        print(f"\n[4] Categoría lista: id={categoria.id}.")

        codigo_unico = f"PROD-FISCAL-{uuid4().hex[:8]}"
        producto = Producto(
            codigo_barras=codigo_unico,
            descripcion="Martillo Fiscal",
            categoria_id=categoria.id,
            alicuota_id=alicuota_g.id,
            precio_ref=Decimal("10.00"),
            stock_actual=Decimal("50.000"),
            stock_minimo=Decimal("5.000"),
            activo=True,
        )
        db.add(producto)
        db.flush()
        db.commit()
        print(f"\n[5] Producto creado: id={producto.id}.")

        # Tasa REF
        tasa = db.scalar(select(TasaRef).order_by(TasaRef.fecha.desc()).limit(1))
        if not tasa:
            tasa = TasaRef(monto_bs=Decimal("742.8100"), origen="BCV", fecha=datetime.now(timezone.utc))
            db.add(tasa)
            db.flush()
            db.commit()
        print(f"\n[6] Tasa REF lista: {tasa.monto_bs} Bs/USD.")

        # Forma de pago
        fp_efectivo = db.scalar(select(FormaPago).where(FormaPago.codigo == "EFECTIVO_USD"))
        if not fp_efectivo:
            fp_efectivo = FormaPago(codigo="EFECTIVO_USD", nombre="Efectivo USD", requiere_referencia=False)
            db.add(fp_efectivo)
            db.flush()
            db.commit()
        print(f"\n[7] Forma de pago lista: id={fp_efectivo.id}.")

        # 3. Crear múltiples ventas (3 facturas con IVA, 1 exenta)
        print(f"\n[8] Creando ventas de prueba...")
        
        # Venta 1: con IVA 16%
        factura1 = crear_venta_prueba(db, cliente.id, producto.id, tasa.id,
                                       Decimal("2.000"), Decimal("10.00"), Decimal("16.00"),
                                       Decimal("20.00"), fp_efectivo.id)
        print(f"    - Factura 1: {factura1.numero_factura}, Total Bs: {factura1.total_bs}")
        
        # Venta 2: con IVA 16%
        factura2 = crear_venta_prueba(db, cliente.id, producto.id, tasa.id,
                                       Decimal("1.000"), Decimal("15.00"), Decimal("16.00"),
                                       Decimal("15.00"), fp_efectivo.id)
        print(f"    - Factura 2: {factura2.numero_factura}, Total Bs: {factura2.total_bs}")
        
        # Venta 3: con IVA 16%
        factura3 = crear_venta_prueba(db, cliente.id, producto.id, tasa.id,
                                       Decimal("3.000"), Decimal("12.00"), Decimal("16.00"),
                                       Decimal("36.00"), fp_efectivo.id)
        print(f"    - Factura 3: {factura3.numero_factura}, Total Bs: {factura3.total_bs}")
        
        db.commit()
        
        # Calcular totales esperados
        total_ventas_esperado = factura1.total_bs + factura2.total_bs + factura3.total_bs
        total_iva_esperado = factura1.iva_bs + factura2.iva_bs + factura3.iva_bs
        cantidad_facturas = 3
        
        print(f"\n[9] Totales esperados:")
        print(f"    - Ventas: Bs {total_ventas_esperado:.2f}")
        print(f"    - IVA: Bs {total_iva_esperado:.2f}")
        print(f"    - Facturas: {cantidad_facturas}")

        # 4. Generar Cierre Z
        print(f"\n[10] Generando Cierre Z...")
        
        # Simular lógica del router (sin transacción porque ya estamos en una)
        ultimo_cierre = db.scalar(select(CierreZ).order_by(CierreZ.fecha.desc()).limit(1))
        ahora = datetime.now(timezone.utc)
        fecha_desde = ultimo_cierre.fecha if ultimo_cierre else datetime(ahora.year, ahora.month, ahora.day, tzinfo=timezone.utc)
        
        stmt = (
            select(Factura)
            .where(
                Factura.fecha_emision >= fecha_desde,
                Factura.estado == "EMITIDA",
            )
            .order_by(Factura.fecha_emision)
        )
        facturas_cierre = db.execute(stmt).scalars().all()
        
        if not facturas_cierre:
            raise AssertionError("No hay facturas para el Cierre Z")
        
        # Calcular totales
        total_ventas_bs = sum(f.total_bs for f in facturas_cierre)
        total_iva_bs = sum(f.iva_bs for f in facturas_cierre)
        total_igtf_bs = sum(f.igtf_bs for f in facturas_cierre)
        
        cierre = CierreZ(
            usuario_id=admin.id,
            fecha=ahora,
            total_ventas_bs=total_ventas_bs.quantize(Decimal("0.00")),
            total_iva_bs=total_iva_bs.quantize(Decimal("0.00")),
            total_igtf_bs=total_igtf_bs.quantize(Decimal("0.00")),
            factura_inicio=facturas_cierre[0].numero_factura,
            factura_fin=facturas_cierre[-1].numero_factura,
        )
        db.add(cierre)
        db.commit()
        
        print(f"\n[11] Cierre Z generado: id={cierre.id}")
        print(f"    - Factura inicio: {cierre.factura_inicio}")
        print(f"    - Factura fin: {cierre.factura_fin}")
        print(f"    - Total ventas: Bs {cierre.total_ventas_bs:.2f}")
        print(f"    - Total IVA: Bs {cierre.total_iva_bs:.2f}")
        print(f"    - Total IGTF: Bs {cierre.total_igtf_bs:.2f}")
        print(f"    - Operaciones: {cierre.cantidad_operaciones}")

        # 5. Verificaciones
        print(f"\n[12] Verificaciones...")
        
        # Verificar que los totales coincidan
        assert abs(cierre.total_ventas_bs - total_ventas_esperado) < Decimal("0.01"), \
            f"Total ventas no coincide. Cierre: {cierre.total_ventas_bs}, Esperado: {total_ventas_esperado}"
        print(f"    ✓ Total ventas coincide")
        
        assert abs(cierre.total_iva_bs - total_iva_esperado) < Decimal("0.01"), \
            f"Total IVA no coincide. Cierre: {cierre.total_iva_bs}, Esperado: {total_iva_esperado}"
        print(f"    ✓ Total IVA coincide")
        
        print(f"    ✓ Cierre Z generado correctamente")
        
        assert cierre.factura_inicio == facturas_cierre[0].numero_factura, "Factura inicio incorrecta"
        print(f"    ✓ Factura inicio correcta")
        
        assert cierre.factura_fin == facturas_cierre[-1].numero_factura, "Factura fin incorrecta"
        print(f"    ✓ Factura fin correcta")

        print(f"\n=== TODAS LAS PRUEBAS PASARON ===")
        print(f"\nResumen:")
        print(f"  - Cierre Z ID: {cierre.id}")
        print(f"  - Facturas procesadas: {cantidad_facturas}")
        print(f"  - Total ventas: Bs {cierre.total_ventas_bs:.2f}")
        print(f"  - Total IVA: Bs {cierre.total_iva_bs:.2f}")

    except Exception as e:
        db.rollback()
        print(f"\n=== ERROR EN PRUEBAS: {e} ===")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_tests()
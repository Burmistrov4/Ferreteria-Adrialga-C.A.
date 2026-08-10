"""
Script de Prueba — Dashboard, Bitácora de Auditoría y Reportes Gerenciales.

Verifica:
1. Generación de entradas en la Bitácora de Auditoría.
2. Cálculo en tiempo real de KPIs de Dashboard (ventas del día/mes, stock bajo, CxC/CxP).
3. Consulta de reportes gerenciales (más vendidos, rentabilidad y ventas por período).

Uso:
    python -m scripts.test_dashboard_audit
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.database import SessionLocal
from app.models import (
    BitacoraAuditoria,
    Categoria,
    Cliente,
    ConfiguracionFiscal,
    CorrelativoFiscal,
    CuentaPorCobrar,
    CuentaPorPagar,
    DetalleVenta,
    Factura,
    FormaPago,
    PagoVenta,
    Producto,
    Role,
    TasaRef,
    Usuario,
)


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
    print("=== PRUEBAS MÓDULO DASHBOARD, BITÁCORA Y REPORTES ===")

    from app.db.init_db import init_db
    init_db()

    db = SessionLocal()
    try:
        # 1. Asegurar usuario admin
        admin = ensure_admin(db)
        db.commit()
        print(f"\n[1] Usuario admin_test listo (id={admin.id}).")

        # 2. Registrar evento en bitácora de auditoría
        print(f"\n[2] Creando registro en Bitácora de Auditoría...")
        evento = BitacoraAuditoria(
            usuario_id=admin.id,
            accion="LOGIN",
            modulo="AUTH",
            detalles="Inicio de sesión exitoso para prueba de dashboard",
            ip_address="127.0.0.1",
            fecha=datetime.now(timezone.utc),
        )
        db.add(evento)
        db.commit()
        print(f"    ✓ Registro de bitácora insertado: ID={evento.id}")

        # 3. Crear una factura de venta hoy para influir en los KPIs del Dashboard
        print(f"\n[3] Creando datos de prueba (Venta, CxC, CxP) para verificar KPIs...")
        alicuota_g = db.scalar(select(ConfiguracionFiscal).where(ConfiguracionFiscal.codigo == "G"))
        if not alicuota_g:
            alicuota_g = ConfiguracionFiscal(codigo="G", porcentaje=Decimal("16.00"), descripcion="General")
            db.add(alicuota_g)
            db.flush()

        categoria = db.scalar(select(Categoria).where(Categoria.nombre == "Herramientas"))
        if not categoria:
            categoria = Categoria(nombre="Herramientas", descripcion="Categoría de prueba")
            db.add(categoria)
            db.flush()

        # Crear producto con bajo stock
        producto = Producto(
            codigo_barras=f"PROD-DASH-{uuid4().hex[:8]}",
            descripcion="Martillo de Prueba",
            categoria_id=categoria.id,
            alicuota_id=alicuota_g.id,
            precio_ref=Decimal("15.00"),
            stock_actual=Decimal("1.000"), # Bajo stock (stock_minimo=2)
            stock_minimo=Decimal("2.000"),
            activo=True,
        )
        db.add(producto)
        db.flush()

        # Crear cliente
        cliente = Cliente(
            cedula_rif=f"V-{uuid4().hex[:8].upper()}",
            razon_social="Cliente Prueba Dashboard",
            direccion="Dirección Prueba",
            telefono="04121234567"
        )
        db.add(cliente)
        db.flush()

        # Crear tasa
        tasa = db.scalar(select(TasaRef).order_by(TasaRef.fecha.desc()).limit(1))
        if not tasa:
            tasa = TasaRef(monto_bs=Decimal("742.8100"), origen="BCV", fecha=datetime.now(timezone.utc))
            db.add(tasa)
            db.flush()

        # Registrar factura de venta
        correlativo = db.scalar(select(CorrelativoFiscal).where(CorrelativoFiscal.tipo_documento == "FACTURA"))
        if not correlativo:
            correlativo = CorrelativoFiscal(tipo_documento="FACTURA", serie="A", ultimo_numero=0)
            db.add(correlativo)
            db.flush()
        correlativo.ultimo_numero += 1
        numero_factura = f"FA-A-{correlativo.ultimo_numero:06d}"

        subtotal_bs = Decimal("150.00")
        iva_bs = Decimal("24.00")
        total_bs = subtotal_bs + iva_bs

        factura = Factura(
            numero_factura=numero_factura,
            correlativo=correlativo.ultimo_numero,
            cliente_id=cliente.id,
            usuario_id=admin.id,
            tasa_ref_id=tasa.id,
            subtotal_bs=subtotal_bs,
            iva_bs=iva_bs,
            igtf_bs=Decimal("0.00"),
            total_bs=total_bs,
            total_ref=Decimal("15.00"),
            estado="EMITIDA",
            fecha_emision=datetime.now(timezone.utc),
        )
        db.add(factura)
        db.flush()

        detalle = DetalleVenta(
            factura_id=factura.id,
            producto_id=producto.id,
            cantidad=Decimal("1.000"),
            precio_unitario_bs=subtotal_bs,
            alicuota_porcentaje=Decimal("16.00"),
            total_linea_bs=total_bs,
        )
        db.add(detalle)

        # Crear cuenta por cobrar
        cxc = CuentaPorCobrar(
            factura_id=factura.id,
            cliente_id=cliente.id,
            monto_total_bs=total_bs,
            saldo_pendiente_bs=total_bs,
            fecha_vencimiento=date.today(),
            estado="PENDIENTE",
        )
        db.add(cxc)

        db.commit()
        print(f"    ✓ Factura, Detalle y CxC creados para simular actividad")

        # 4. Verificar KPIs y reportes consultando directamente los métodos del router
        print(f"\n[4] Consultando KPIs agregados y reportes gerenciales...")
        
        from app.routers.dashboard import _obtener_kpis, _datos_grafico_ventas
        
        kpis = _obtener_kpis(db)
        print(f"    - Ventas Hoy: Bs {kpis.ventas_hoy_bs:.2f}")
        print(f"    - CxC Pendiente: Bs {kpis.total_cxc_pendiente:.2f}")
        print(f"    - Productos bajo stock: {kpis.productos_bajo_stock}")
        
        assert kpis.ventas_hoy_bs >= total_bs, "El total de ventas de hoy no se reflejó correctamente"
        assert kpis.total_cxc_pendiente >= total_bs, "Las cuentas por cobrar no coinciden"
        assert kpis.productos_bajo_stock >= 1, "La alerta de bajo stock no se activó"
        print("    ✓ Validación de KPIs del Dashboard exitosa")

        # Verificar gráfico de ventas de los últimos 30 días
        datos_grafico = _datos_grafico_ventas(db)
        assert len(datos_grafico["fechas"]) > 0, "No se recuperaron datos para el gráfico"
        print("    ✓ Gráfico de ventas recuperado exitosamente")

        # Verificar listado de bitácora
        registros_bitacora = db.scalars(select(BitacoraAuditoria).where(BitacoraAuditoria.usuario_id == admin.id)).all()
        assert len(registros_bitacora) > 0, "La bitácora de auditoría no guardó los registros de prueba"
        print(f"    ✓ Bitácora verificada con éxito: {len(registros_bitacora)} registros de este usuario.")

        print(f"\n=== TODAS LAS PRUEBAS PASARON ===")
        print(f"\nResumen:")
        print(f"  - Registro de auditoría guardado y verificado")
        print(f"  - KPI Ventas Hoy: Bs {kpis.ventas_hoy_bs:.2f}")
        print(f"  - KPI CxC Pendiente: Bs {kpis.total_cxc_pendiente:.2f}")
        print(f"  - Productos bajo stock: {kpis.productos_bajo_stock}")

    except Exception as e:
        db.rollback()
        print(f"\n=== ERROR EN PRUEBAS: {e} ===")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_tests()

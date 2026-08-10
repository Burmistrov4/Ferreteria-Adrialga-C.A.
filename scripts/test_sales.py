"""
Script de Prueba — Módulo de Ventas, POS y Facturación.

Verifica el flujo completo de una venta:
1. Validación de stock.
2. Asignación de correlativo fiscal.
3. Creación de factura y detalle_ventas.
4. Descuento de stock y generación de Kardex SALIDA.
5. Registro de pagos.
6. Generación de Cuenta por Cobrar si hay saldo pendiente.

Uso:
    python -m scripts.test_sales
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
    CuentaPorCobrar,
    DetalleVenta,
    Factura,
    FormaPago,
    KardexMovimiento,
    Producto,
    PagoVenta,
    Role,
    TasaRef,
    Usuario,
)
from app.models.inventory import Producto as ProductoModel


def ensure_admin(db: Session) -> Usuario:
    """Crea usuario admin temporal si no existe."""
    admin = db.scalar(select(Usuario).where(Usuario.username == "admin_test"))
    if admin:
        return admin

    rol = db.scalar(select(Role).where(Role.nombre == "Superusuario"))
    if not rol:
        # Crear rol si no existe
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
    print("=== PRUEBAS MÓDULO VENTAS Y POS ===")

    # Crear tablas si no existen
    from app.db.init_db import init_db
    init_db()

    db = SessionLocal()
    try:
        # 1. Asegurar usuario admin
        admin = ensure_admin(db)
        db.commit()
        print(f"\n[1] Usuario admin_test listo (id={admin.id}).")

        # 2. Asegurar datos básicos (alícuota, cliente, producto, tasa, formas de pago)
        alicuota = db.scalar(select(ConfiguracionFiscal).where(ConfiguracionFiscal.codigo == "G"))
        if not alicuota:
            alicuota = ConfiguracionFiscal(
                codigo="G", porcentaje=Decimal("16.00"), descripcion="General"
            )
            db.add(alicuota)
            db.flush()
            db.commit()
        print(f"\n[2] Alícuota G {alicuota.porcentaje}% encontrada.")

        # Cliente de prueba (único por RIF)
        rif_unico = f"V-{uuid4().hex[:8].upper()}"
        cliente = Cliente(
            cedula_rif=rif_unico,
            razon_social="Cliente Test",
            direccion="Dirección de prueba",
            telefono="04120000000",
        )
        db.add(cliente)
        db.flush()
        db.commit()
        print(f"\n[3] Cliente creado: id={cliente.id}, RIF={cliente.cedula_rif}.")

        # Categoría y producto de prueba
        categoria = db.scalar(select(Categoria).where(Categoria.nombre == "Herramientas"))
        if not categoria:
            categoria = Categoria(nombre="Herramientas", descripcion="Categoría de prueba")
            db.add(categoria)
            db.flush()
            db.commit()
        print(f"\n[4] Categoría lista: id={categoria.id}.")

        codigo_unico = f"PROD-{uuid4().hex[:8]}"
        producto = Producto(
            codigo_barras=codigo_unico,
            descripcion="Martillo de prueba POS",
            categoria_id=categoria.id,
            alicuota_id=alicuota.id,
            precio_ref=Decimal("10.00"),
            stock_actual=Decimal("50.000"),
            stock_minimo=Decimal("5.000"),
            activo=True,
        )
        db.add(producto)
        db.flush()
        db.commit()
        print(f"\n[5] Producto creado: id={producto.id}, stock_inicial={producto.stock_actual}.")

        # Tasa REF
        tasa = db.scalar(select(TasaRef).order_by(TasaRef.fecha.desc()).limit(1))
        if not tasa:
            tasa = TasaRef(
                monto_bs=Decimal("742.8100"),
                origen="BCV",
                fecha=datetime.now(timezone.utc),
            )
            db.add(tasa)
            db.flush()
            db.commit()
        print(f"\n[6] Tasa REF lista: {tasa.monto_bs} Bs/USD.")

        # Formas de pago
        fp_efectivo = db.scalar(select(FormaPago).where(FormaPago.codigo == "EFECTIVO_USD"))
        if not fp_efectivo:
            fp_efectivo = FormaPago(
                codigo="EFECTIVO_USD", nombre="Efectivo USD", requiere_referencia=False
            )
            db.add(fp_efectivo)
            db.flush()
            db.commit()
        print(f"\n[7] Forma de pago lista: id={fp_efectivo.id}.")

        # 3. Procesar una venta completa
        cantidad_venta = Decimal("2.000")
        precio_usd = Decimal("10.00")
        tasa_iva = Decimal("16.00")
        subtotal_usd = precio_usd * cantidad_venta  # 20.00
        iva_usd = subtotal_usd * (tasa_iva / Decimal("100"))  # 3.20
        total_usd = subtotal_usd + iva_usd  # 23.20
        monto_pago_usd = Decimal("15.00")  # Pagamos solo 15 USD de 23.20

        # Cálculos en Bs - formatear exactamente a 2 decimales para evitar problemas de precisión en SQLite
        subtotal_bs = Decimal(f"{float(subtotal_usd * tasa.monto_bs):.2f}")
        iva_bs = Decimal(f"{float(iva_usd * tasa.monto_bs):.2f}")
        igtf_bs = Decimal("0.00")
        # total_bs debe ser EXACTAMENTE la suma para pasar el CHECK constraint
        total_bs = subtotal_bs + iva_bs + igtf_bs
        # Asegurar que total_bs tenga exactamente 2 decimales
        total_bs = Decimal(f"{float(total_bs):.2f}")
        total_ref = Decimal(f"{float(total_bs / tasa.monto_bs):.2f}")

        print(f"\n[8] Procesando venta:")
        print(f"    - Producto: {producto.descripcion} (id={producto.id})")
        print(f"    - Cantidad: {cantidad_venta}")
        print(f"    - Precio USD: {precio_usd}")
        print(f"    - Subtotal USD: {subtotal_usd:.2f}")
        print(f"    - IVA USD: {iva_usd:.2f}")
        print(f"    - Total USD: {total_usd:.2f}")
        print(f"    - Total Bs: {total_bs:.2f}")
        print(f"    - Pago USD: {monto_pago_usd:.2f}")

        # Simular la lógica del router de ventas (transacción manual)
        try:
            # Validar stock
            if producto.stock_actual < cantidad_venta:
                raise AssertionError("Stock insuficiente.")

            # Correlativo
            correlativo = db.scalar(
                select(CorrelativoFiscal).where(
                    CorrelativoFiscal.tipo_documento == "FACTURA",
                    CorrelativoFiscal.serie == "A",
                )
            )
            if not correlativo:
                correlativo = CorrelativoFiscal(
                    tipo_documento="FACTURA", serie="A", ultimo_numero=0
                )
                db.add(correlativo)
                db.flush()

            numero_factura = f"FA-A-{correlativo.ultimo_numero + 1:06d}"
            correlativo.ultimo_numero += 1

            # Factura (valores ya calculados antes)
            factura = Factura(
                numero_factura=numero_factura,
                correlativo=correlativo.ultimo_numero,
                cliente_id=cliente.id,
                usuario_id=admin.id,
                tasa_ref_id=tasa.id,
                subtotal_bs=Decimal(str(subtotal_bs)),
                iva_bs=Decimal(str(iva_bs)),
                igtf_bs=Decimal("0.00"),
                total_bs=Decimal(str(total_bs)),
                total_ref=Decimal(str(total_ref)),
                estado="EMITIDA",
                fecha_emision=datetime.now(timezone.utc),
            )
            db.add(factura)
            db.flush()

            # Detalle de venta
            detalle = DetalleVenta(
                factura_id=factura.id,
                producto_id=producto.id,
                cantidad=cantidad_venta,
                precio_unitario_bs=precio_usd * tasa.monto_bs,
                alicuota_porcentaje=tasa_iva,
                total_linea_bs=precio_usd * cantidad_venta * tasa.monto_bs,
            )
            db.add(detalle)

            # Actualizar stock
            producto.stock_actual -= cantidad_venta

            # Kardex SALIDA
            kardex = KardexMovimiento(
                producto_id=producto.id,
                tipo_movimiento="SALIDA",
                cantidad=cantidad_venta,
                costo_ref=precio_usd * tasa.monto_bs,
                origen_id=factura.id,
                fecha=datetime.now(timezone.utc),
            )
            db.add(kardex)

            # Pago
            pago = PagoVenta(
                factura_id=factura.id,
                forma_pago_id=fp_efectivo.id,
                monto_origen=monto_pago_usd,
                moneda="USD",
                tasa_cambio=tasa.monto_bs,
                monto_bs=monto_pago_usd * tasa.monto_bs,
                referencia=None,
            )
            db.add(pago)

            # Cuenta por cobrar (saldo pendiente)
            saldo_pendiente = total_bs - (monto_pago_usd * tasa.monto_bs)
            if saldo_pendiente > 0:
                cxc = CuentaPorCobrar(
                    factura_id=factura.id,
                    cliente_id=cliente.id,
                    monto_total_bs=total_bs,
                    saldo_pendiente_bs=saldo_pendiente,
                    estado="PENDIENTE",
                    fecha_vencimiento=date.today(),
                )
                db.add(cxc)

            db.commit()
        except Exception:
            db.rollback()
            raise
        print(f"\n[9] Venta procesada: factura {numero_factura} (id={factura.id}).")

        # 4. Verificaciones post-venta
        factura_db = db.get(Factura, factura.id)
        assert factura_db is not None, "Factura no encontrada."
        assert factura_db.numero_factura == numero_factura, "Número de factura incorrecto."
        print(f"\n[10] Factura verificada: {factura_db.numero_factura}.")

        detalle_db = db.scalar(select(DetalleVenta).where(DetalleVenta.factura_id == factura.id))
        assert detalle_db is not None, "Detalle de venta no encontrado."
        assert detalle_db.cantidad == cantidad_venta, "Cantidad en detalle no coincide."
        print(f"\n[11] DetalleVenta OK: id={detalle_db.id}, cantidad={detalle_db.cantidad}.")

        kardex_db = db.scalar(select(KardexMovimiento).where(KardexMovimiento.producto_id == producto.id))
        assert kardex_db is not None, "Kardex no generado."
        assert kardex_db.tipo_movimiento == "SALIDA", f"Tipo Kardex incorrecto: {kardex_db.tipo_movimiento}"
        assert kardex_db.cantidad == cantidad_venta, "Cantidad Kardex no coincide."
        print(f"\n[12] Kardex SALIDA OK: id={kardex_db.id}, cantidad={kardex_db.cantidad}.")

        producto_db = db.get(Producto, producto.id)
        stock_esperado = Decimal("50.000") - cantidad_venta
        assert producto_db.stock_actual == stock_esperado, f"Stock no descontado. Esperado: {stock_esperado}, Actual: {producto_db.stock_actual}"
        print(f"\n[13] Stock actualizado: {producto_db.stock_actual}.")

        pago_db = db.scalar(select(PagoVenta).where(PagoVenta.factura_id == factura.id))
        assert pago_db is not None, "Pago no registrado."
        assert pago_db.monto_bs == monto_pago_usd * tasa.monto_bs, "Monto de pago incorrecto."
        print(f"\n[14] Pago registrado OK: id={pago_db.id}, monto_bs={pago_db.monto_bs}.")

        cxc_db = db.scalar(select(CuentaPorCobrar).where(CuentaPorCobrar.factura_id == factura.id))
        assert cxc_db is not None, "Cuenta por cobrar no generada."
        assert cxc_db.estado == "PENDIENTE", f"Estado CxC incorrecto: {cxc_db.estado}"
        print(f"\n[15] Cuenta por Cobrar generada: id={cxc_db.id}, saldo={cxc_db.saldo_pendiente_bs}.")

        print("\n=== TODAS LAS PRUEBAS PASARON ===")

    except Exception as e:
        db.rollback()
        print(f"\n=== ERROR EN PRUEBAS: {e} ===")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_tests()
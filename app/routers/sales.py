"""
Router de Ventas y POS — Facturación, Cobros y Kardex.

Rutas:
- GET  /pos                    : Vista principal del POS.
- GET  /pos/buscar-producto    : Búsqueda rápida de productos (JSON/HTMX).
- GET  /pos/buscar-cliente     : Búsqueda rápida de clientes (JSON/HTMX).
- POST /pos/procesar-venta     : Procesa una venta completa (transacción atómica).
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.database import get_db
from app.models.inventory import KardexMovimiento, Producto
from app.models.sales import (
    Cliente,
    CorrelativoFiscal,
    CuentaPorCobrar,
    DetalleVenta,
    Factura,
    FormaPago,
    PagoVenta,
    TasaRef,
)
from app.schemas.sales import VentaCreate, VentaItemCreate, VentaPagoCreate
from app.services.fiscal_service import get_active_caja

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ============================================================
# VISTAS
# ============================================================

@router.get("/pos", response_class=HTMLResponse)
async def pos_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "ver")),
):
    """Vista principal del POS/Terminal de Ventas."""
    tasa = db.scalar(
        select(TasaRef).order_by(TasaRef.fecha.desc()).limit(1)
    )

    # Detectar petición HTMX para evitar duplicar el sidebar
    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="sales/pos.html",
        context={"usuario": usuario, "tasa": tasa, "base_template": base_template},
    )


# ============================================================
# BÚSQUEDAS (JSON/HTMX)
# ============================================================

@router.get("/pos/devoluciones", response_class=HTMLResponse)
async def devoluciones_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "ver")),
):
    """Vista de Devoluciones y Notas de Crédito."""
    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="sales/devoluciones.html",
        context={"usuario": usuario, "base_template": base_template},
    )


@router.get("/configuracion", response_class=HTMLResponse)
async def configuracion_index(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "ver")),
):
    """Vista de configuración de tasa de cambio y parámetros fiscales."""
    tasa = db.scalar(select(TasaRef).order_by(TasaRef.fecha.desc()).limit(1))
    historico = db.execute(
        select(TasaRef).order_by(TasaRef.fecha.desc()).limit(10)
    ).scalars().all()

    is_htmx = request.headers.get("HX-Request") == "true"
    base_template = "partial.html" if is_htmx else "base.html"

    return templates.TemplateResponse(
        request=request,
        name="configuracion/index.html",
        context={
            "usuario": usuario,
            "tasa": tasa,
            "historico": historico,
            "base_template": base_template,
        },
    )


@router.post("/pos/tasa-ref", response_class=JSONResponse)
async def actualizar_tasa_ref(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "editar")),
):
    """Registra una nueva tasa de cambio USD/VES en el histórico."""
    form = await request.form()
    monto_bs = Decimal(form.get("monto_bs") or "0")
    origen = (form.get("origen") or "MANUAL").strip().upper()

    if monto_bs <= 0:
        return JSONResponse(
            status_code=400,
            content={"error": "El monto de la tasa debe ser mayor a cero."},
        )

    tasa = TasaRef(
        monto_bs=monto_bs,
        origen=origen,
        fecha=datetime.now(timezone.utc),
    )
    db.add(tasa)
    db.commit()
    db.refresh(tasa)

    return JSONResponse(
        status_code=201,
        content={"ok": True, "id": tasa.id, "monto_bs": float(tasa.monto_bs)},
    )


@router.get("/pos/buscar-producto", response_class=JSONResponse)
async def buscar_producto(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "ver")),
    q: str = Query(default="", description="Texto de búsqueda"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Busca productos por código de barras, SKU o descripción.
    Devuelve resultados ligeros para autocompletado.
    """
    if not q.strip():
        return {"productos": []}

    like = f"%{q.strip()}%"
    stmt = (
        select(Producto)
        .where(
            Producto.activo.is_(True),
            or_(
                Producto.codigo_barras.ilike(like),
                Producto.descripcion.ilike(like),
            ),
        )
        .order_by(Producto.codigo_barras)
        .limit(limit)
    )

    productos = db.execute(stmt).scalars().all()
    return {
        "productos": [
            {
                "id": p.id,
                "codigo_barras": p.codigo_barras,
                "descripcion": p.descripcion,
                "precio_ref": float(p.precio_ref),
                "stock_actual": float(p.stock_actual),
            }
            for p in productos
        ]
    }


@router.put("/pos/clientes/{cliente_id}", response_class=JSONResponse)
async def actualizar_cliente(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "editar")),
):
    """Actualiza datos de un cliente con validación de RIF/Cédula duplicado."""
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        return JSONResponse(status_code=404, content={"error": "Cliente no encontrado"})

    form = await request.form()

    if "cedula_rif" in form:
        cedula_rif = (form.get("cedula_rif") or "").strip()
        if not cedula_rif:
            return JSONResponse(
                status_code=400,
                content={"error": "El RIF/Cédula es obligatorio."},
            )
        existente = db.scalar(
            select(Cliente).where(Cliente.cedula_rif == cedula_rif, Cliente.id != cliente_id)
        )
        if existente:
            return JSONResponse(
                status_code=409,
                content={"error": f"Ya existe un cliente con RIF/Cédula {cedula_rif}."},
            )
        cliente.cedula_rif = cedula_rif
    if "razon_social" in form:
        cliente.razon_social = (form.get("razon_social") or "").strip()
    if "direccion" in form:
        cliente.direccion = (form.get("direccion") or "").strip()
    if "telefono" in form:
        cliente.telefono = (form.get("telefono") or "").strip()
    if "email" in form:
        cliente.email = (form.get("email") or "").strip()
    if "limite_credito" in form:
        try:
            cliente.limite_credito = Decimal(form.get("limite_credito") or "0.00")
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"error": "Límite de crédito inválido."},
            )

    db.commit()
    return JSONResponse(status_code=200, content={"ok": True, "id": cliente.id})


@router.get("/pos/buscar-cliente", response_class=JSONResponse)
async def buscar_cliente(
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "ver")),
    q: str = Query(default="", description="RIF/Cédula o nombre"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Busca clientes por RIF/Cédula o razón social."""
    if not q.strip():
        return {"clientes": []}

    like = f"%{q.strip()}%"
    stmt = (
        select(Cliente)
        .where(
            or_(
                Cliente.cedula_rif.ilike(like),
                Cliente.razon_social.ilike(like),
            )
        )
        .order_by(Cliente.razon_social)
        .limit(limit)
    )

    clientes = db.execute(stmt).scalars().all()
    return {
        "clientes": [
            {
                "id": c.id,
                "cedula_rif": c.cedula_rif,
                "razon_social": c.razon_social,
            }
            for c in clientes
        ]
    }


# ============================================================
# CLIENTES (API rápida para el POS)
# ============================================================

@router.get("/api/clientes/buscar", response_class=JSONResponse)
async def api_buscar_cliente_por_cedula(
    cedula: str = Query(..., description="Cédula/RIF del cliente"),
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "ver")),
):
    """
    Busca un cliente por Cédula/RIF para autocompletar en el POS.

    Devuelve 404 con `encontrado: False` si no existe para que el
    frontend despliegue el modal de registro rápido en caliente.
    """
    cedula_limpia = cedula.strip()
    if not cedula_limpia:
        return JSONResponse(
            status_code=400,
            content={"error": "La cédula/RIF es obligatoria."},
        )

    cliente = db.scalar(select(Cliente).where(Cliente.cedula_rif == cedula_limpia))
    if not cliente:
        return JSONResponse(status_code=404, content={"encontrado": False})

    return JSONResponse(
        status_code=200,
        content={
            "encontrado": True,
            "cliente": {
                "id": cliente.id,
                "cedula_rif": cliente.cedula_rif,
                "razon_social": cliente.razon_social,
                "telefono": cliente.telefono,
                "direccion": cliente.direccion,
            },
        },
    )


@router.post("/api/clientes/rapido", response_class=JSONResponse)
async def api_registrar_cliente_rapido(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "crear")),
):
    """
    Registra un cliente rápido desde el POS sin perder la venta en curso.

    Campos obligatorios: Cédula/RIF y Nombre/Razón Social.
    Teléfono y Dirección son opcionales pero recomendados.
    """
    form = await request.form()
    cedula_rif = (form.get("cedula_rif") or "").strip()
    razon_social = (form.get("razon_social") or "").strip()
    telefono = (form.get("telefono") or "").strip()
    direccion = (form.get("direccion") or "").strip()

    if not cedula_rif or not razon_social:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Cédula/RIF y Nombre/Razón Social son obligatorios."
            },
        )

    # Validar duplicado
    existente = db.scalar(select(Cliente).where(Cliente.cedula_rif == cedula_rif))
    if existente:
        return JSONResponse(
            status_code=409,
            content={
                "error": f"Ya existe un cliente con RIF/Cédula {cedula_rif}.",
                "cliente": {
                    "id": existente.id,
                    "cedula_rif": existente.cedula_rif,
                    "razon_social": existente.razon_social,
                },
            },
        )

    cliente = Cliente(
        cedula_rif=cedula_rif,
        razon_social=razon_social,
        telefono=telefono or None,
        direccion=direccion or None,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)

    return JSONResponse(
        status_code=201,
        content={
            "ok": True,
            "cliente": {
                "id": cliente.id,
                "cedula_rif": cliente.cedula_rif,
                "razon_social": cliente.razon_social,
                "telefono": cliente.telefono,
                "direccion": cliente.direccion,
            },
        },
    )


# ============================================================
# PROCESAR VENTA (Transacción Atómica)
# ============================================================

@router.post("/pos/procesar-venta", response_class=JSONResponse)
async def procesar_venta(
    request: Request,
    db: Session = Depends(get_db),
    usuario=Depends(require_permission("ventas", "crear")),
):
    """
    Procesa una venta completa dentro de una transacción atómica.

    Pasos:
    1. Valida stock disponible.
    2. Asigna correlativo fiscal.
    3. Crea factura y detalle_ventas.
    4. Actualiza stock y genera movimientos Kardex (SALIDA).
    5. Registra pagos.
    6. Si hay saldo pendiente, genera Cuenta por Cobrar.
    """
    try:
        data = await request.json()
        venta = VentaCreate(**data)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Datos inválidos: {e}"})

    # Transacción atómica con try/except
    try:
        # Obtener tasa del día
        tasa_ref = db.scalar(select(TasaRef).order_by(TasaRef.fecha.desc()).limit(1))
        if not tasa_ref:
            return JSONResponse(status_code=400, content={"error": "No hay tasa de cambio registrada."})

        sesion_caja = get_active_caja(db, usuario.id)
        if not sesion_caja:
            return JSONResponse(
                status_code=400,
                content={"error": "No hay sesión de caja abierta para este usuario."},
            )

        # 1. Validar stock y preparar cálculos
        productos_validados = []
        subtotal_bs = Decimal("0.00")
        iva_bs = Decimal("0.00")

        for item in venta.items:
            prod = db.get(Producto, item.producto_id)
            if not prod or not prod.activo:
                return JSONResponse(
                    status_code=400,
                    content={"error": f"Producto {item.producto_id} no válido."},
                )

            if prod.stock_actual < item.cantidad:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": f"Stock insuficiente para {prod.descripcion}. "
                        f"Disponible: {prod.stock_actual}, solicitado: {item.cantidad}"
                    },
                )

            # Calcular con redondeo explícito a 2 decimales
            precio_unitario_bs = Decimal(f"{float(item.precio_unitario_usd * tasa_ref.monto_bs):.2f}")
            total_linea_bs = Decimal(f"{float(precio_unitario_bs * item.cantidad):.2f}")
            subtotal_bs += total_linea_bs
            iva_linea = Decimal(f"{float(total_linea_bs * (item.tasa_iva / Decimal('100'))):.2f}")
            iva_bs += iva_linea

            productos_validados.append(
                {
                    "producto": prod,
                    "cantidad": item.cantidad,
                    "precio_unitario_bs": precio_unitario_bs,
                    "tasa_iva": item.tasa_iva,
                    "total_linea_bs": total_linea_bs,
                }
            )

        # total_bs debe ser exactamente la suma para pasar CHECKs
        total_bs = subtotal_bs + iva_bs
        total_ref = total_bs / tasa_ref.monto_bs

        # 2. Asignar correlativo fiscal
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

        # 3. Crear factura
        factura = Factura(
            numero_factura=numero_factura,
            correlativo=correlativo.ultimo_numero,
            cliente_id=venta.cliente_id or 1,  # Cliente contado por defecto
            usuario_id=usuario.id,
            tasa_ref_id=tasa_ref.id,
            sesion_caja_id=sesion_caja.id,
            subtotal_bs=subtotal_bs,
            iva_bs=iva_bs,
            igtf_bs=Decimal("0.00"),
            total_bs=total_bs,
            total_ref=total_ref,
            estado="EMITIDA",
            fecha_emision=datetime.now(timezone.utc),
        )
        db.add(factura)
        db.flush()

        # 4. Detalle de ventas y actualización de stock/kardex
        for pv in productos_validados:
            detalle = DetalleVenta(
                factura_id=factura.id,
                producto_id=pv["producto"].id,
                cantidad=pv["cantidad"],
                precio_unitario_bs=pv["precio_unitario_bs"],
                alicuota_porcentaje=pv["tasa_iva"],
                total_linea_bs=pv["total_linea_bs"],
            )
            db.add(detalle)

            # Actualizar stock
            pv["producto"].stock_actual -= pv["cantidad"]

            # Movimiento Kardex SALIDA
            kardex = KardexMovimiento(
                producto_id=pv["producto"].id,
                tipo_movimiento="SALIDA",
                cantidad=pv["cantidad"],
                costo_ref=pv["precio_unitario_bs"],
                origen_id=factura.id,
                fecha=datetime.now(timezone.utc),
            )
            db.add(kardex)

        # 5. Registrar pagos
        total_pagado_bs = Decimal("0.00")
        for pago in venta.pagos:
            monto_usd = pago.monto_usd
            monto_ves = pago.monto_ves

            if monto_ves is not None and monto_ves > 0:
                # Pago directo en bolivares (Pago Movil / Punto / Efectivo VES)
                monto_bs = monto_ves
                monto_origen = monto_ves
                moneda = "BS"
                tasa_cambio = Decimal("1.0000")
            elif monto_usd is not None and monto_usd > 0:
                # Pago en dolares (Efectivo USD) convertido con tasa BCV en tiempo real
                monto_bs = Decimal(f"{float(monto_usd * tasa_ref.monto_bs):.2f}")
                monto_origen = monto_usd
                moneda = "USD"
                tasa_cambio = tasa_ref.monto_bs
            else:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Cada pago debe indicar monto en USD o VES."},
                )

            total_pagado_bs += monto_bs

            pago_venta = PagoVenta(
                factura_id=factura.id,
                forma_pago_id=pago.forma_pago_id,
                monto_origen=monto_origen,
                moneda=moneda,
                tasa_cambio=tasa_cambio,
                monto_bs=monto_bs,
                referencia=pago.referencia,
            )
            db.add(pago_venta)

        # Validar que el total pagado (convertido a moneda base) cubra o supere la venta
        if total_pagado_bs < total_bs:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "El total pagado no cubre el monto de la venta.",
                    "total_bs": float(total_bs),
                    "total_pagado_bs": float(total_pagado_bs),
                    "faltante_bs": float(total_bs - total_pagado_bs),
                },
            )

        # Vuelto/cambio desglosado por moneda (base = bolivares)
        vuelto_bs = total_pagado_bs - total_bs
        vuelto_ref = Decimal("0.00")
        if vuelto_bs > 0:
            vuelto_ref = Decimal(f"{float(vuelto_bs / tasa_ref.monto_bs):.2f}")

        # 6. Cuentas por Cobrar si hay saldo pendiente
        saldo_pendiente = total_bs - total_pagado_bs
        if saldo_pendiente > 0:
            cxc = CuentaPorCobrar(
                factura_id=factura.id,
                cliente_id=venta.cliente_id or 1,
                monto_total_bs=total_bs,
                saldo_pendiente_bs=saldo_pendiente,
                estado="PENDIENTE",
                fecha_vencimiento=date.today(),
            )
            db.add(cxc)

        db.commit()
        db.refresh(factura)
    except Exception:
        db.rollback()
        return JSONResponse(
            status_code=500,
            content={"error": "Error al procesar la venta. Operación revertida."},
        )

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "factura_id": factura.id,
            "numero_factura": numero_factura,
            "total_bs": float(total_bs),
            "total_ref": float(total_ref),
            "total_pagado_bs": float(total_pagado_bs),
            "vuelto_bs": float(vuelto_bs),
            "vuelto_ref": float(vuelto_ref),
        },
    )
# -*- coding: utf-8 -*-
"""Parcheador: lógica de cobro multimoneda para el POS de Adrialga."""
import io
import sys


def patch(path, replacements):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
    had_crlf = "\r\n" in raw
    content = raw.replace("\r\n", "\n")
    for old, new in replacements:
        if old not in content:
            print("NOPE: " + path + " -> " + old[:80])
            sys.exit(1)
        content = content.replace(old, new, 1)
    if had_crlf:
        content = content.replace("\n", "\r\n")
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print("OK: " + path)


# ============================================================
# 1. app/schemas/sales.py — monto_usd pasa a opcional
# ============================================================
patch("app/schemas/sales.py", [
    (
        '''    monto_usd: Decimal = Field(ge=0, description="Monto original en USD o BS")
    monto_ves: Optional[Decimal] = Field(default=None, description="Monto convertido a VES")''',
        '''    monto_usd: Optional[Decimal] = Field(default=None, description="Monto en USD (efectivo USD)")
    monto_ves: Optional[Decimal] = Field(default=None, description="Monto en VES (pago movil, punto o efectivo)")''',
    ),
])

# ============================================================
# 2. app/routers/sales.py — pagos multimoneda + validacion + vuelto
# ============================================================
old_pagos = '''        total_pagado_bs = Decimal("0.00")
        for pago in venta.pagos:
            monto_bs = pago.monto_ves if pago.monto_ves else pago.monto_usd * tasa_ref.monto_bs
            total_pagado_bs += monto_bs

            pago_venta = PagoVenta(
                factura_id=factura.id,
                forma_pago_id=pago.forma_pago_id,
                monto_origen=pago.monto_usd,
                moneda="USD",
                tasa_cambio=tasa_ref.monto_bs,
                monto_bs=monto_bs,
                referencia=pago.referencia,
            )
            db.add(pago_venta)
'''

new_pagos = '''        total_pagado_bs = Decimal("0.00")
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
'''

patch("app/routers/sales.py", [(old_pagos, new_pagos)])

# ============================================================
# 3. Respuesta final con vuelto
# ============================================================
old_resp = '''    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "factura_id": factura.id,
            "numero_factura": numero_factura,
            "total_bs": float(total_bs),
            "total_ref": float(total_ref),
        },
    )'''

new_resp = '''    return JSONResponse(
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
    )'''

patch("app/routers/sales.py", [(old_resp, new_resp)])

print("Patches aplicados correctamente.")
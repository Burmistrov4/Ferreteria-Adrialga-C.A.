"""
Aplicación principal de FastAPI — Ferretería Adrialga, C.A. ERP / POS.

Configura:
- Instancia FastAPI
- Archivos estáticos
- Plantillas Jinja2
- Routers de autenticación y dashboard
- Manejador global de errores 401 (HTTPException con detail)
"""

import asyncio
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import RENDER_EXTERNAL_URL
from app.routers import auth, dashboard, fiscal, inventory, purchases, sales

app = FastAPI(
    title="Ferretería Adrialga C.A. - ERP / POS",
    description=(
        "Sistema ERP/POS para Ferretería Adrialga, C.A. "
        "· RIF J-405837357 · Módulos: POS, Inventario, Compras, "
        "Cuentas por Cobrar/Pagar, Fiscal SENIAT"
    ),
    version="0.1.0",
)

async def self_ping_task():
    """Bucle asíncrono para mantener viva la instancia en Render (evitar reposo)."""
    if not RENDER_EXTERNAL_URL:
        return
    # Espera inicial para permitir que el servidor se levante completamente
    await asyncio.sleep(15)
    async with httpx.AsyncClient() as client:
        while True:
            try:
                url = f"{RENDER_EXTERNAL_URL.rstrip('/')}/health"
                response = await client.get(url, timeout=10.0)
                print(f"[Self-Ping] OK: {url} -> {response.status_code}")
            except Exception as e:
                print(f"[Self-Ping] Error al conectar con {RENDER_EXTERNAL_URL}: {e}")
            # Esperar 10 minutos (600 segundos)
            await asyncio.sleep(600)

@app.on_event("startup")
async def startup_event():
    if RENDER_EXTERNAL_URL:
        print(f"[Lifespan/Startup] Configurando ping automático redundante cada 10 minutos a: {RENDER_EXTERNAL_URL}")
        asyncio.create_task(self_ping_task())

# ---------------------------------------------------------------------------
# Archivos estáticos y plantillas
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(inventory.router)
app.include_router(sales.router)
app.include_router(fiscal.router)
app.include_router(purchases.router)


@app.get("/health", tags=["Sistema"])
def health() -> dict:
    """Endpoint de verificación de salud del servicio."""
    return {"status": "ok", "servicio": "Ferretería Adrialga ERP/POS", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Manejador global de errores de autenticación (401)
# ---------------------------------------------------------------------------
@app.exception_handler(401)
async def auth_exception_handler(request: Request, exc):
    """
    Maneja errores de autenticación.

    - Si la petición viene de HTMX, devuelve HX-Redirect: /login.
    - Si es navegación estándar, redirige a /login.
    """
    hx_request = request.headers.get("HX-Request", "").lower() == "true"
    if hx_request:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response
    return RedirectResponse(url="/login", status_code=303)
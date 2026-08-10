"""Script de verificación del servidor en vivo (Uvicorn)."""

import urllib.request

try:
    with urllib.request.urlopen("http://127.0.0.1:8000/login", timeout=5) as r:
        body = r.read().decode("utf-8", errors="replace")
        print(f"GET /login [LIVE]: HTTP {r.status} | {r.headers.get('Content-Type')} | {len(body)} bytes")
        print(f"Contiene 'Iniciar Sesión': {'Iniciar Sesión' in body}")
        print("VERIFICACION EN VIVO OK")
except Exception as e:
    print(f"ERROR conectando al servidor: {e}")
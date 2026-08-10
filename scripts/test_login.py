"""Script de prueba del flujo de autenticación — Ferretería Adrialga, C.A."""

from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    client = TestClient(app, follow_redirects=False)

    # 1. GET /login debe cargar el formulario
    r = client.get("/login")
    print(f"GET /login: {r.status_code} | HTML: {len(r.text)} bytes")
    assert r.status_code == 200, "Login page no cargó correctamente"
    assert "Iniciar Sesión" in r.text, "Falta el título de login en el HTML"

    # 2. POST /login con credenciales correctas
    r = client.post("/login", data={"username": "admin", "password": "Admin1234*"})
    print(f"POST /login: {r.status_code}")
    print(f"  Set-Cookie: {r.headers.get('set-cookie', 'SIN COOKIE')[:100]}")
    cookie = client.cookies.get("adrialga_session")
    assert cookie, "No se estableció la cookie adrialga_session"

    # 3. GET / con cookie debe cargar el dashboard
    r2 = client.get("/")
    print(f"GET / (con cookie): {r2.status_code} | HTML: {len(r2.text)} bytes")
    assert r2.status_code == 200, "Dashboard no cargó con cookie válida"
    assert "Panel de Control" in r2.text or "ADRIALGA" in r2.text, "Dashboard no renderizó"

    # 4. POST /login con credenciales incorrectas
    r3 = client.post("/login", data={"username": "admin", "password": "incorrecta"})
    print(f"POST /login (incorrecto): {r3.status_code}")
    assert "Credenciales incorrectas" in r3.text, "No mostró mensaje de error"

    # 5. GET /login con sesión activa debe redirigir a /
    r4 = client.get("/login")
    print(f"GET /login (con sesión): {r4.status_code}")
    assert r4.status_code == 303, "No redirigió al dashboard con sesión activa"

    # 6. GET /logout debe inactivar sesión y redirigir a /login
    r5 = client.get("/logout")
    print(f"GET /logout: {r5.status_code}")
    assert r5.status_code == 303, "Logout no redirigió correctamente"

    # 7. GET / sin sesión debe redirigir a /login
    r6 = client.get("/")
    print(f"GET / (sin cookie): {r6.status_code} -> {r6.headers.get('location')}")
    assert r6.status_code == 303, "No redirigió a /login sin sesión"

    print("\n=== TODAS LAS PRUEBAS DE LOGIN PASARON CORRECTAMENTE ===")


if __name__ == "__main__":
    main()
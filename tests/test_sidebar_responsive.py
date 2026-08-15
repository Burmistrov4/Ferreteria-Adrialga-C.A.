"""Pruebas de interacción del sidebar responsive.

Verifica los requerimientos:
1. Detección de pantallas con ancho <= 768px (móviles y tabletas).
2. Evento 'click' en enlaces del menú (.sidebar .nav-link).
3. Al hacer clic en un enlace, se remueve la clase 'open' del #sidebar y 'active' del .overlay.
4. Mantener scroll suave y transición visual de cierre que no bloquee la navegación.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
JS_PATH = BASE_DIR / "app" / "static" / "js" / "main.js"
CSS_PATH = BASE_DIR / "app" / "static" / "css" / "styles.css"
BASE_HTML_PATH = BASE_DIR / "app" / "templates" / "base.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_js_detecta_pantallas_hasta_768px():
    """El JS usa <= 768px para detectar móviles y tabletas."""
    js = _read(JS_PATH)
    assert "768" in js
    assert "window.innerWidth <= 768" in js


def test_js_escucha_clicks_en_enlaces_del_menu():
    """El JS escucha 'click' en todos los enlaces de navegación del sidebar."""
    js = _read(JS_PATH)
    assert "sidebar.querySelectorAll('.nav-link')" in js
    assert "addEventListener('click'" in js


def test_js_cierra_sidebar_al_click_en_enlace():
    """Al hacer clic en un enlace se llama closeSidebar (remueve .open y .active)."""
    js = _read(JS_PATH)
    assert "function closeSidebar" in js
    nav_handler = js.split("querySelectorAll('.nav-link')")[1]
    nav_handler = nav_handler.split("});")[0]
    assert "closeSidebar()" in nav_handler


def test_js_close_sidebar_remueve_clases_open_y_active():
    """closeSidebar remueve 'open' del #sidebar y 'active' del overlay."""
    js = _read(JS_PATH)
    close_impl = js.split("function closeSidebar")[1].split("}")[0]
    assert "classList.remove('open')" in close_impl
    assert "classList.remove('active')" in close_impl


def test_js_cierra_solo_en_pantallas_moviles():
    """El cierre al navegar se condiciona a window.innerWidth <= 768."""
    js = _read(JS_PATH)
    nav_block = js.split("querySelectorAll('.nav-link')")[1]
    nav_block = nav_block.split("// Tooltips")[0]
    assert "window.innerWidth <= 768" in nav_block


def test_css_media_query_768px_detecta_moviles():
    """El CSS aplica estilos responsive para pantallas <= 768px."""
    css = _read(CSS_PATH)
    assert "@media (max-width: 768px)" in css


def test_css_sidebar_se_oculta_fuera_de_pantalla():
    """El sidebar se fija y se desplaza fuera de pantalla en móviles."""
    css = _read(CSS_PATH)
    media_block = css.split("@media (max-width: 768px)")[1]
    media_block = media_block.split("@keyframes")[0]
    assert "position: fixed" in media_block
    assert "transform: translateX(-100%)" in media_block
    assert "transition: transform" in media_block
    assert "cubic-bezier" in media_block


def test_css_sidebar_abierto_se_muestra_con_transicion():
    """La clase .open muestra el sidebar con transición y will-change."""
    css = _read(CSS_PATH)
    media_block = css.split("@media (max-width: 768px)")[1]
    media_block = media_block.split("@keyframes")[0]
    assert ".sidebar.open" in media_block
    assert "transform: translateX(0)" in media_block
    assert "will-change: transform" in media_block


def test_css_overlay_tiene_transicion_suave():
    """El overlay tiene transición suave de opacidad (no bloquea navegación)."""
    css = _read(CSS_PATH)
    media_block = css.split("@media (max-width: 768px)")[1]
    media_block = media_block.split("@keyframes")[0]
    assert "background: rgba(0, 0, 0, 0.5)" in media_block
    assert "transition: opacity 0.3s ease" in media_block
    assert ".sidebar-overlay.active" in media_block


def test_base_html_carga_el_script_principal():
    """base.html carga main.js (script responsable del sidebar)."""
    html = _read(BASE_HTML_PATH)
    assert "js/main.js" in html
    assert "sidebarToggle" in html
    assert 'id="sidebar"' in html


def test_main_js_esta_sintacticamente_balanceado():
    """main.js está balanceado en llaves y paréntesis (sin código incompleto)."""
    js = _read(JS_PATH)
    assert js.count("{") == js.count("}")
    assert js.count("(") == js.count(")")
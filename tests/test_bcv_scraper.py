import ssl
from decimal import Decimal
from datetime import datetime
import httpx
import pytest

from app.services import bcv_scraper as bcv


def test_parsear_monto_bs_valido():
    assert bcv._parsear_monto_bs("1.234,56") == Decimal("1234.56")
    assert bcv._parsear_monto_bs("42,50") == Decimal("42.50")


def test_parsear_monto_bs_invalido():
    assert bcv._parsear_monto_bs("no-un-monto") is None


def test_parsear_fecha_valida():
    fecha = bcv._parsear_fecha("5", "agosto", "2026")
    assert fecha == datetime(2026, 8, 5)


def test_parsear_fecha_mes_invalido():
    assert bcv._parsear_fecha("5", "mes-inventado", "2026") is None


def test_extraer_tasa_desde_html_valido():
    html = """
    <div class="view-tipo-de-cambio">
        <span>USD</span>
        <strong> 42,50 </strong>
        <span>Fecha Valor: lunes, 5 agosto 2026</span>
    </div>
    """
    tasa = bcv._extraer_tasa_desde_html(html)
    assert tasa is not None
    assert tasa.monto_bs == Decimal("42.50")
    assert tasa.fecha == datetime(2026, 8, 5)


def test_extraer_tasa_desde_html_sin_fecha():
    html = """
    <div class="view-tipo-de-cambio">
        <span>USD</span>
        <strong> 42,50 </strong>
    </div>
    """
    tasa = bcv._extraer_tasa_desde_html(html)
    assert tasa is not None
    assert tasa.monto_bs == Decimal("42.50")
    assert isinstance(tasa.fecha, datetime)


def test_extraer_tasa_desde_html_invalido():
    html = "<div>No hay tasas de cambio aqui</div>"
    assert bcv._extraer_tasa_desde_html(html) is None


def test_obtener_tasa_bcv_exito(monkeypatch):
    class FakeResponse:
        def __init__(self, text):
            self.text = text
        def raise_for_status(self):
            pass

    html = """
    <div class="view-tipo-de-cambio">
        <span>USD</span>
        <strong> 42,50 </strong>
        <span>Fecha Valor: lunes, 5 de agosto de 2026</span>
    </div>
    """
    monkeypatch.setattr(bcv.httpx, "get", lambda *args, **kwargs: FakeResponse(html))
    tasa = bcv.obtener_tasa_bcv()
    assert tasa is not None
    assert tasa.monto_bs == Decimal("42.50")


def test_obtener_tasa_bcv_fallback_ssl(monkeypatch):
    class FakeResponse:
        def __init__(self, text):
            self.text = text
        def raise_for_status(self):
            pass

    html = """
    <div class="view-tipo-de-cambio">
        <span>USD</span>
        <strong> 43,10 </strong>
    </div>
    """
    intentos = []

    def fake_get(url, verify=None, **kwargs):
        intentos.append(verify)
        if verify is not False:
            raise ssl.SSLError("SSL verification failed")
        return FakeResponse(html)

    monkeypatch.setattr(bcv.httpx, "get", fake_get)
    tasa = bcv.obtener_tasa_bcv()
    assert tasa is not None
    assert tasa.monto_bs == Decimal("43.10")
    assert len(intentos) == 2
    assert intentos[1] is False


def test_obtener_tasa_bcv_falla_completa(monkeypatch):
    def fake_get(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(bcv.httpx, "get", fake_get)
    tasa = bcv.obtener_tasa_bcv()
    assert tasa is None

import httpx

from app.services import seniat_service

def test_formatear_rif_digits_asume_prefijo_v():
    assert seniat_service._formatear_rif("28036972") == "V28036972"

def test_formatear_rif_con_prefijo_valido_mantiene_prefijo():
    assert seniat_service._formatear_rif("j-12345678-9") == "J12345678-9".replace("-", "")

def test_formatear_rif_invalido_devuelve_none():
    assert seniat_service._formatear_rif("XYZ123") is None

def test_parsear_respuesta_extrae_campos_correctamente():
    html = """
    <rif:rif>J-12345678-9</rif:rif>
    <rif:nombre>Proveedor Ejemplo C.A.</rif:nombre>
    <rif:agenteretencioniva>si</rif:agenteretencioniva>
    <rif:rate>100</rif:rate>
    """
    resultado = seniat_service._parsear_respuesta(html)
    assert resultado["nombre"] == "Proveedor Ejemplo C.A."
    assert resultado["es_contribuyente_especial"] is True
    assert resultado["porcentaje_retencion"] == 100.0

def test_consultar_rif_invalido_documento_devuelve_error():
    resultado = seniat_service.consultar_rif("INVALIDO")
    assert resultado["success"] is False
    assert "Documento inválido" in resultado["error"]

def test_consultar_rif_returns_success_for_valid_html(monkeypatch):
    class FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    html_response = """
    <rif:rif>V12345678</rif:rif>
    <rif:nombre>Proveedor Ejemplo C.A.</rif:nombre>
    <rif:agenteretencioniva>no</rif:agenteretencioniva>
    <rif:rate>0</rif:rate>
    """
    monkeypatch.setattr(
        seniat_service.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse(html_response),
    )

    resultado = seniat_service.consultar_rif("12345678")
    assert resultado["success"] is True
    assert resultado["rif"] == "V12345678"
    assert resultado["nombre"] == "Proveedor Ejemplo C.A."
    assert resultado["es_contribuyente_especial"] is False
    assert resultado["porcentaje_retencion"] == 0.0

def test_consultar_rif_request_error_returns_false(monkeypatch):
    def raise_http_error(*args, **kwargs):
        raise httpx.HTTPError("timeout")

    monkeypatch.setattr(seniat_service.httpx, "get", raise_http_error)

    resultado = seniat_service.consultar_rif("J-12345678-9")
    assert resultado["success"] is False
    assert "No se pudo consultar el SENIAT" in resultado["error"]
"""
Servicio de Validación de RIF (SENIAT) — Ferretería Adrialga, C.A.

Consulta los datos fiscales de un contribuyente en el portal público del SENIAT.

URL de consulta:
    http://contribuyente.seniat.gob.ve/BuscaRif/BuscaRif.jsp?p_rif={rif_formateado}

Estrategia:
1. Formatea el RIF/Cédula (prefijos V, E, J, G, P).
2. Realiza la consulta con timeout estricto (3s) y User-Agent Mozilla/5.0.
3. Parsea la respuesta XML/HTML para extraer nombre, condición de
   contribuyente especial y tasa de retención.
4. Si falla, devuelve un diccionario de fallo suave sin bloquear el flujo.
"""

import re
from typing import Optional

import httpx

# URL del portal público del SENIAT
SENIAT_URL = "http://contribuyente.seniat.gob.ve/BuscaRif/BuscaRif.jsp"

# Prefijos válidos de RIF venezolano
PREFIJOS_VALIDOS = {"V", "E", "J", "G", "P"}

# Timeout estricto: 3 segundos para no pausar el flujo de caja
TIMEOUT = 3.0

# Cabeceras de red
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}


def _limpiar_documento(documento: str) -> str:
    """Elimina puntos, guiones y espacios de la cadena del documento."""
    return re.sub(r"[.\-\s]", "", documento or "").strip()


def _formatear_rif(documento: str) -> Optional[str]:
    """
    Formatea un RIF o Cédula a la estructura esperada por el SENIAT.

    - Si el string contiene solo dígitos (ej: 28036972), asume prefijo 'V'.
    - Acepta prefijos V, E, J, G, P.
    - Retorna None si el documento no es válido.
    """
    limpio = _limpiar_documento(documento)
    if not limpio:
        return None

    # Si todo son dígitos, asumir prefijo V (cédula venezolana)
    if limpio.isdigit():
        return f"V{limpio}"

    # Si tiene prefijo válido, asegurar mayúsculas
    if len(limpio) >= 2 and limpio[0].upper() in PREFIJOS_VALIDOS:
        prefijo = limpio[0].upper()
        resto = limpio[1:]
        if resto.isdigit():
            return f"{prefijo}{resto}"

    return None


def _parsear_respuesta(html: str) -> dict:
    """
    Parsea el XML/HTML de respuesta del SENIAT.

    Extrae:
    - Razón Social / Nombre (<rif:nombre>)
    - Agente de retención IVA (<rif:agenteretencioniva>)
    - Tasa de retención (<rif:rate>)
    """
    resultado = {
        "rif": None,
        "nombre": None,
        "es_contribuyente_especial": False,
        "porcentaje_retencion": 0,
    }

    # Extraer nombre entre etiquetas rif:nombre
    match_nombre = re.search(r"<rif:nombre>([^<]+)</rif:nombre>", html, re.I)
    if match_nombre:
        resultado["nombre"] = match_nombre.group(1).strip()

    # Extraer agente de retención IVA
    match_agente = re.search(
        r"<rif:agenteretencioniva>([^<]+)</rif:agenteretencioniva>", html, re.I
    )
    if match_agente:
        valor = match_agente.group(1).strip().lower()
        resultado["es_contribuyente_especial"] = valor in ("true", "1", "si", "sí")

    # Extraer tasa de retención
    match_rate = re.search(r"<rif:rate>([^<]+)</rif:rate>", html, re.I)
    if match_rate:
        try:
            resultado["porcentaje_retencion"] = float(match_rate.group(1).strip())
        except (ValueError, TypeError):
            resultado["porcentaje_retencion"] = 0

    # Si no se encontró el nombre, el RIF no existe
    if not resultado["nombre"]:
        return {}

    return resultado


def consultar_rif(documento: str) -> dict:
    """
    Consulta los datos fiscales de un RIF/Cédula en el SENIAT.

    Retorna:
    - Éxito: {"success": True, "rif": "...", "nombre": "...",
              "es_contribuyente_especial": bool, "porcentaje_retencion": float}
    - Fallo: {"success": False, "error": "No se pudo consultar el SENIAT"}
    """
    rif_formateado = _formatear_rif(documento)
    if not rif_formateado:
        return {
            "success": False,
            "error": "Documento inválido. Ingrese un RIF o cédula válida.",
        }

    try:
        # Realizar la consulta con timeout estricto
        resp = httpx.get(
            SENIAT_URL,
            params={"p_rif": rif_formateado},
            timeout=TIMEOUT,
            headers=HEADERS,
            follow_redirects=True,
        )
        resp.raise_for_status()

        # Parsear la respuesta
        datos = _parsear_respuesta(resp.text)
        if not datos:
            return {
                "success": False,
                "error": "No se pudo consultar el SENIAT",
            }

        return {
            "success": True,
            "rif": rif_formateado,
            "nombre": datos["nombre"],
            "es_contribuyente_especial": datos["es_contribuyente_especial"],
            "porcentaje_retencion": datos["porcentaje_retencion"],
        }

    except (httpx.TimeoutException, httpx.HTTPError, Exception):
        # Fallo suave: no bloquear el flujo
        return {
            "success": False,
            "error": "No se pudo consultar el SENIAT",
        }
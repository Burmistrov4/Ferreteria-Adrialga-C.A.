"""
Servicio de Scraping de la Tasa de Cambio del BCV — Ferretería Adrialga, C.A.

Extrae la tasa USD/REF vigente del sitio web del Banco Central de Venezuela
(https://www.bcv.org.ve/) con fallback SSL y parseo por regex.

Estrategia:
1. Intento 1: Petición con `certifi` y verificación SSL activa.
2. Intento 2 (Fallback): Petición con `verify=False` e `insecure_fallback`
   (desactivando advertencias de urllib3).
3. Parseo del HTML con BeautifulSoup y regex para tasa USD y fecha de valor.
"""

import re
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

import certifi
import httpx
import urllib3
from bs4 import BeautifulSoup

# Desactivar advertencias de urllib3 para el fallback SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# URL objetivo del BCV
BCV_URL = "https://www.bcv.org.ve/"

# Regex para extraer la tasa USD (formato venezolano: 1.234,56)
REGEX_TASA_USD = r"\bUSD\b\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]+)"

# Regex para extraer la fecha de valor (ej: "Fecha Valor: lunes, 5 de agosto de 2026")
REGEX_FECHA = (
    r"Fecha\s+Valor:\s*[A-Za-zÁÉÍÓÚáéíóúñÑ]+,\s*"
    r"(\d{1,2})\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+(\d{4})"
)

# Mapeo de meses en español a número
MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


@dataclass
class TasaBCV:
    """Resultado del scraping de la tasa BCV."""
    monto_bs: Decimal
    fecha: datetime
    origen: str = "BCV"


def _parsear_monto_bs(texto: str) -> Optional[Decimal]:
    """
    Convierte un texto de tasa venezolano (ej: "1.234,56") a Decimal.

    - Elimina puntos de miles.
    - Reemplaza coma decimal por punto.
    """
    try:
        # Quitar puntos de miles y reemplazar coma decimal
        limpio = texto.replace(".", "").replace(",", ".")
        return Decimal(limpio)
    except (InvalidOperation, ValueError):
        return None


def _parsear_fecha(dia: str, mes: str, anio: str) -> Optional[datetime]:
    """Convierte día/mes/año en español a datetime."""
    try:
        mes_num = MESES_ES.get(mes.lower())
        if not mes_num:
            return None
        return datetime(int(anio), mes_num, int(dia))
    except (ValueError, TypeError):
        return None


def _extraer_tasa_desde_html(html: str) -> Optional[TasaBCV]:
    """
    Extrae la tasa USD y la fecha de valor desde el HTML del BCV.

    Usa BeautifulSoup para localizar el bloque de la tasa y regex
    para extraer los valores numéricos.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Buscar el bloque que contiene "USD" (tasa de cambio)
    # El BCV muestra la tasa en un div con clase "view-tipo-de-cambio"
    bloque_tasa = soup.find("div", class_=re.compile(r"tipo-de-cambio|dolar|usd", re.I))

    # Si no se encuentra el bloque, buscar en todo el HTML
    texto_busqueda = bloque_tasa.get_text(" ", strip=True) if bloque_tasa else html

    # Extraer tasa USD
    match_tasa = re.search(REGEX_TASA_USD, texto_busqueda)
    if not match_tasa:
        return None

    monto_bs = _parsear_monto_bs(match_tasa.group(1))
    if not monto_bs or monto_bs <= 0:
        return None

    # Extraer fecha de valor
    fecha = None
    match_fecha = re.search(REGEX_FECHA, texto_busqueda)
    if match_fecha:
        fecha = _parsear_fecha(match_fecha.group(1), match_fecha.group(2), match_fecha.group(3))

    # Si no se encontró fecha, usar la fecha actual
    if not fecha:
        fecha = datetime.now(timezone.utc)

    return TasaBCV(monto_bs=monto_bs, fecha=fecha)


def obtener_tasa_bcv() -> Optional[TasaBCV]:
    """
    Obtiene la tasa de cambio USD/REF del BCV.

    Intento 1: Petición con `certifi` y verificación SSL activa.
    Intento 2 (Fallback): Petición con `verify=False` e `insecure_fallback`.

    Retorna un objeto `TasaBCV` o `None` si no se pudo obtener.
    """
    # Intento 1: SSL verificado con certifi
    try:
        resp = httpx.get(
            BCV_URL,
            verify=certifi.where(),
            timeout=15.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "es-ES,es;q=0.9",
            },
        )
        resp.raise_for_status()
        tasa = _extraer_tasa_desde_html(resp.text)
        if tasa:
            return tasa
    except (httpx.HTTPError, ssl.SSLError, Exception):
        pass  # Continuar al fallback

    # Intento 2: Fallback SSL desactivado (insecure_fallback)
    try:
        resp = httpx.get(
            BCV_URL,
            verify=False,
            timeout=15.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "es-ES,es;q=0.9",
            },
        )
        resp.raise_for_status()
        tasa = _extraer_tasa_desde_html(resp.text)
        if tasa:
            return tasa
    except (httpx.HTTPError, ssl.SSLError, Exception):
        pass

    return None
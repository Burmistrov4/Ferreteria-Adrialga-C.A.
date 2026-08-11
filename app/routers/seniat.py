"""
Router de Validación de RIF (SENIAT) — Ferretería Adrialga, C.A.

Expone el endpoint público para consultar datos fiscales de un
contribuyente (nombre, condición de contribuyente especial, tasa
de retención) a partir de un RIF o Cédula.

Rutas:
- GET /api/seniat/consultar/{documento} : Consulta datos fiscales en el SENIAT
"""

from fastapi import APIRouter

from app.services.seniat_service import consultar_rif

router = APIRouter(prefix="/api/seniat", tags=["SENIAT"])


@router.get("/consultar/{documento}")
def consultar_seniat(documento: str) -> dict:
    """
    Consulta los datos fiscales de un RIF/Cédula en el SENIAT.

    Ejemplo de respuesta exitosa:
    {
        "success": true,
        "rif": "V280369720",
        "nombre": "NOMBRE Y APELLIDO",
        "es_contribuyente_especial": false,
        "porcentaje_retencion": 0
    }

    Ejemplo de fallo (timeout / no encontrado):
    {"success": false, "error": "No se pudo consultar el SENIAT"}
    """
    return consultar_rif(documento)
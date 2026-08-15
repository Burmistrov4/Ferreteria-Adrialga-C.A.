"""
Servicio de integración con modelo GLM-5.2 de Z-AI vía NVIDIA NIM API.

Configura un cliente OpenAI-compatible que apunta a la API de NVIDIA.
Las credenciales se leen exclusivamente desde variables de entorno:
  - NVIDIA_API_KEY  : clave de API de NVIDIA NIM
  - NVIDIA_BASE_URL : endpoint base (default: https://integrate.api.nvidia.com/v1)
  - GLM_MODEL_NAME  : nombre del modelo (default: z-ai/glm-5.2)

Uso:
    from app.services.llm_service import chat_completion, stream_chat

    # Respuesta completa (no streaming)
    respuesta = asyncio.run(chat_completion(
        mensajes=[{"role": "user", "content": "¿Cuál es la diferencia entre IVA y IR?"}],
    ))

    # Respuesta en streaming (generador asíncrono)
    async for chunk in stream_chat(mensajes=[{"role": "user", "content": "Hola"}]):
        print(chunk, end="")
"""

import os
from typing import Any, AsyncIterator, Dict, List, Optional

from openai import AsyncOpenAI, OpenAI


class LLMConfigError(RuntimeError):
    """Error de configuración: falta la API Key o variable de entorno requerida."""


def _get_api_key() -> str:
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise LLMConfigError(
            "NVIDIA_API_KEY no está configurada en las variables de entorno. "
            "Añade la variable al archivo .env con tu clave real de NVIDIA NIM."
        )
    return api_key


def _get_base_url() -> str:
    return os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")


def _get_model() -> str:
    return os.getenv("GLM_MODEL_NAME", "z-ai/glm-5.2")


# ---------------------------------------------------------------------------
# Clientes (singleton implícito por módulo)
# ---------------------------------------------------------------------------
client: OpenAI = OpenAI(
    api_key=_get_api_key() if os.getenv("NVIDIA_API_KEY") else "placeholder",
    base_url=_get_base_url(),
)

async_client: AsyncOpenAI = AsyncOpenAI(
    api_key=_get_api_key() if os.getenv("NVIDIA_API_KEY") else "placeholder",
    base_url=_get_base_url(),
)


def get_model() -> str:
    """Devuelve el nombre del modelo GLM configurado."""
    return _get_model()


# ---------------------------------------------------------------------------
# Funciones públicas
# ---------------------------------------------------------------------------

def chat_completion(
    mensajes: List[Dict[str, str]],
    temperatura: float = 0.7,
    max_tokens: int = 2048,
    top_p: float = 0.95,
    model: Optional[str] = None,
) -> str:
    """
    Genera una respuesta completa (no streaming) usando el modelo GLM-5.2.

    Args:
        mensajes: Lista de mensajes en formato OpenAI
                  [{"role": "user", "content": "..."}, ...].
        temperatura: Control de aleatoriedad (0.0 a 2.0).
        max_tokens: Número máximo de tokens a generar.
        top_p: Nucleus sampling (0.0 a 1.0).
        model: Nombre del modelo (usa el valor de GLM_MODEL_NAME por defecto).

    Returns:
        El contenido del mensaje de la respuesta como string.

    Raises:
        LLMConfigError: Si NVIDIA_API_KEY no está configurada.
    """
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise LLMConfigError(
            "NVIDIA_API_KEY no está configurada en las variables de entorno. "
            "Añade la variable al archivo .env con tu clave real de NVIDIA NIM."
        )

    nombre_modelo = model or _get_model()

    response = client.chat.completions.create(
        model=nombre_modelo,
        messages=mensajes,
        temperature=temperatura,
        max_tokens=max_tokens,
        top_p=top_p,
        stream=False,
    )

    return response.choices[0].message.content


async def stream_chat(
    mensajes: List[Dict[str, str]],
    temperatura: float = 0.7,
    max_tokens: int = 2048,
    top_p: float = 0.95,
    model: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Genera una respuesta en streaming (asíncrona) usando el modelo GLM-5.2.

    Args:
        mensajes: Lista de mensajes en formato OpenAI.
        temperatura: Control de aleatoriedad (0.0 a 2.0).
        max_tokens: Número máximo de tokens a generar.
        top_p: Nucleus sampling (0.0 a 1.0).
        model: Nombre del modelo (usa el valor de GLM_MODEL_NAME por defecto).

    Yields:
        Fragmentos de texto (strings) de la respuesta a medida que llegan.

    Raises:
        LLMConfigError: Si NVIDIA_API_KEY no está configurada.
    """
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise LLMConfigError(
            "NVIDIA_API_KEY no está configurada en las variables de entorno. "
            "Añade la variable al archivo .env con tu clave real de NVIDIA NIM."
        )

    nombre_modelo = model or _get_model()

    stream = await async_client.chat.completions.create(
        model=nombre_modelo,
        messages=mensajes,
        temperature=temperatura,
        max_tokens=max_tokens,
        top_p=top_p,
        stream=True,
    )

    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


# ---------------------------------------------------------------------------
# Utilidad: verificar conectividad / configuración
# ---------------------------------------------------------------------------

def health_check() -> Dict[str, Any]:
    """
    Verifica que la configuración del servicio LLM sea correcta.

    Returns:
        Dict con información de configuración (sin exponer la API key).
    """
    api_key_configured = bool(os.getenv("NVIDIA_API_KEY"))
    return {
        "service": "GLM-5.2 (NVIDIA NIM)",
        "base_url": _get_base_url(),
        "model": _get_model(),
        "api_key_configured": api_key_configured,
    }

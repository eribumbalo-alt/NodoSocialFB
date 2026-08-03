"""Puerta unica hacia cualquier modelo de lenguaje.

El resto del proyecto no sabe si detras hay Ollama corriendo local
o la API de NVIDIA. Solo llama a completar().

Configuracion en el archivo .env:

    PROVEEDOR=nvidia          # o "ollama"
    NVIDIA_API_KEY=nvapi-...
    MODELO_NVIDIA=nvidia/nemotron-3-super-120b-a12b
    MODELO_OLLAMA=llama3.2:3b

Para probar la conexion sin tocar el resto del proyecto:

    python scripts/proveedor.py
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ARCHIVO_ENV = BASE_DIR / ".env"


# ==========================================================
# CONFIGURACION
# ==========================================================

def cargar_env() -> None:
    """Lee el .env sin depender de librerias externas."""

    if not ARCHIVO_ENV.exists():
        return

    for linea in ARCHIVO_ENV.read_text(encoding="utf-8").splitlines():

        linea = linea.strip()

        if not linea or linea.startswith("#") or "=" not in linea:
            continue

        clave, valor = linea.split("=", 1)
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")

        # Lo que ya este en el entorno tiene prioridad.
        if clave and clave not in os.environ:
            os.environ[clave] = valor


cargar_env()

PROVEEDOR = os.environ.get("PROVEEDOR", "ollama").lower()

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.environ.get(
    "NVIDIA_BASE_URL",
    "https://integrate.api.nvidia.com/v1",
)

MODELO_NVIDIA = os.environ.get(
    "MODELO_NVIDIA",
    "nvidia/nemotron-3-super-120b-a12b",
)

MODELO_OLLAMA = os.environ.get("MODELO_OLLAMA", "llama3.2:3b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


# ----------------------------------------------------------
# LIMITES
# ----------------------------------------------------------
# El endpoint gratuito de NVIDIA ronda las 40 solicitudes por
# minuto. Se deja margen: 30 por minuto = 2 segundos entre
# llamadas. Si aparecen muchos errores 429, subí este numero.

SEGUNDOS_ENTRE_LLAMADAS = 2.0

MAXIMO_REINTENTOS = 4
ESPERA_BASE = 3.0
TIMEOUT_SEGUNDOS = 90


# ==========================================================
# ESTADISTICAS
# ==========================================================

class Contador:
    """Lleva la cuenta de llamadas, errores y tiempo."""

    def __init__(self) -> None:
        self.llamadas = 0
        self.reintentos = 0
        self.errores = 0
        self.segundos = 0.0

    def resumen(self) -> str:

        promedio = (
            self.segundos / self.llamadas
            if self.llamadas
            else 0.0
        )

        return (
            f"Llamadas: {self.llamadas} | "
            f"Reintentos: {self.reintentos} | "
            f"Errores: {self.errores} | "
            f"Tiempo total: {self.segundos:.1f}s | "
            f"Promedio: {promedio:.1f}s"
        )


contador = Contador()

_ultima_llamada = 0.0


def esperar_turno() -> None:
    """Frena para no pasarse del limite de solicitudes por minuto."""

    global _ultima_llamada

    if PROVEEDOR != "nvidia":
        return

    transcurrido = time.time() - _ultima_llamada
    falta = SEGUNDOS_ENTRE_LLAMADAS - transcurrido

    if falta > 0:
        time.sleep(falta)

    _ultima_llamada = time.time()


# ==========================================================
# CLIENTES
# ==========================================================

_cliente_nvidia = None
_cliente_ollama = None


def cliente_nvidia():

    global _cliente_nvidia

    if _cliente_nvidia is not None:
        return _cliente_nvidia

    if not NVIDIA_API_KEY:
        raise RuntimeError(
            "Falta NVIDIA_API_KEY en el archivo .env.\n"
            "Consegui la clave en build.nvidia.com "
            "(boton 'Get API Key'). Empieza con nvapi-"
        )

    try:
        from openai import OpenAI

    except ImportError:
        raise RuntimeError(
            "Falta la libreria openai. Instalala con:\n"
            "    pip install openai"
        )

    _cliente_nvidia = OpenAI(
        base_url=NVIDIA_BASE_URL,
        api_key=NVIDIA_API_KEY,
        timeout=TIMEOUT_SEGUNDOS,
    )

    return _cliente_nvidia


def cliente_ollama():

    global _cliente_ollama

    if _cliente_ollama is not None:
        return _cliente_ollama

    from ollama import Client

    _cliente_ollama = Client(host=OLLAMA_HOST)

    return _cliente_ollama


# ==========================================================
# ERRORES REINTENTABLES
# ==========================================================

# 429 = demasiadas solicitudes. 5xx = problema del servidor.
# Ambos se resuelven esperando. Un 401 o un 400 no: reintentar
# solo hace perder tiempo.

TEXTOS_REINTENTABLES = (
    "429",
    "rate limit",
    "too many requests",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "connection",
    "overloaded",
)


def conviene_reintentar(error: Exception) -> bool:

    mensaje = str(error).lower()

    return any(t in mensaje for t in TEXTOS_REINTENTABLES)


def es_error_de_esquema(error: Exception) -> bool:
    """Detecta que el modelo no soporta salida estructurada."""

    mensaje = str(error).lower()

    marcas = (
        "response_format",
        "json_schema",
        "not supported",
        "unsupported",
        "guided",
    )

    return any(m in mensaje for m in marcas)


# ==========================================================
# LLAMADAS
# ==========================================================

def _llamar_nvidia(
    prompt_sistema: str,
    prompt_usuario: str,
    esquema: dict | None,
    usar_esquema: bool,
) -> str:

    cliente = cliente_nvidia()

    parametros = {
        "model": MODELO_NVIDIA,
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario},
        ],
        "temperature": 0,
        "max_tokens": 900,
    }

    if esquema and usar_esquema:
        parametros["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "clasificacion",
                "strict": True,
                "schema": esquema,
            },
        }

    elif esquema:
        # Plan B: el modelo no acepta json_schema, se le pide
        # JSON por instruccion.
        parametros["response_format"] = {"type": "json_object"}

    respuesta = cliente.chat.completions.create(**parametros)

    return (respuesta.choices[0].message.content or "").strip()


def _llamar_ollama(
    prompt_sistema: str,
    prompt_usuario: str,
    esquema: dict | None,
) -> str:

    cliente = cliente_ollama()

    parametros = {
        "model": MODELO_OLLAMA,
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario},
        ],
        "options": {"temperature": 0},
    }

    if esquema:
        parametros["format"] = esquema

    respuesta = cliente.chat(**parametros)

    return (respuesta.message.content or "").strip()


# Se recuerda si el modelo rechazo el esquema, para no volver
# a intentarlo en cada llamada.
_esquema_soportado = True


def completar(
    prompt_sistema: str,
    prompt_usuario: str,
    esquema: dict | None = None,
) -> str:
    """Manda los prompts al modelo y devuelve el texto crudo.

    esquema: JSON schema para forzar el formato de salida.
             Si el modelo no lo soporta, se degrada solo.

    Reintenta ante errores de velocidad o del servidor.
    """

    global _esquema_soportado

    ultimo_error: Exception | None = None

    for intento in range(MAXIMO_REINTENTOS):

        try:
            esperar_turno()

            inicio = time.time()

            if PROVEEDOR == "nvidia":
                contenido = _llamar_nvidia(
                    prompt_sistema,
                    prompt_usuario,
                    esquema,
                    _esquema_soportado,
                )
            else:
                contenido = _llamar_ollama(
                    prompt_sistema,
                    prompt_usuario,
                    esquema,
                )

            contador.segundos += time.time() - inicio
            contador.llamadas += 1

            if not contenido:
                raise RuntimeError("El modelo respondio vacio.")

            return contenido

        except Exception as error:

            ultimo_error = error

            # El modelo no acepta json_schema: se reintenta
            # sin el, una sola vez y para siempre.
            if _esquema_soportado and es_error_de_esquema(error):

                print(
                    "[AVISO] El modelo no soporta json_schema. "
                    "Se pasa a modo JSON simple."
                )

                _esquema_soportado = False
                continue

            if not conviene_reintentar(error):
                contador.errores += 1
                raise

            if intento < MAXIMO_REINTENTOS - 1:

                espera = ESPERA_BASE * (2 ** intento)

                contador.reintentos += 1

                print(
                    f"   [reintento {intento + 1}/"
                    f"{MAXIMO_REINTENTOS - 1}] "
                    f"esperando {espera:.0f}s..."
                )

                time.sleep(espera)

    contador.errores += 1

    raise RuntimeError(
        f"Fallaron {MAXIMO_REINTENTOS} intentos. "
        f"Ultimo error: {ultimo_error}"
    )


def extraer_json(contenido: str) -> dict:
    """Convierte la respuesta en diccionario.

    Tolera que el modelo agregue ```json o texto alrededor.
    """

    texto = contenido.strip()

    if texto.startswith("```"):
        texto = texto.split("```")[1]
        if texto.startswith("json"):
            texto = texto[4:]
        texto = texto.strip()

    try:
        return json.loads(texto)

    except json.JSONDecodeError:
        pass

    # Ultimo recurso: agarrar lo que hay entre la primera
    # llave y la ultima.
    inicio = texto.find("{")
    fin = texto.rfind("}")

    if inicio != -1 and fin > inicio:
        return json.loads(texto[inicio:fin + 1])

    raise ValueError(
        f"No se pudo leer JSON de la respuesta:\n{contenido[:400]}"
    )


def info() -> str:

    if PROVEEDOR == "nvidia":
        clave = "configurada" if NVIDIA_API_KEY else "FALTA"
        return (
            f"Proveedor: NVIDIA | Modelo: {MODELO_NVIDIA} | "
            f"API key: {clave}"
        )

    return f"Proveedor: Ollama (local) | Modelo: {MODELO_OLLAMA}"


# ==========================================================
# PRUEBA DE CONEXION
# ==========================================================

ESQUEMA_PRUEBA = {
    "type": "object",
    "properties": {
        "es_reclamo": {"type": "boolean"},
        "motivo": {"type": "string"},
    },
    "required": ["es_reclamo", "motivo"],
}

CASOS = [
    (
        "true",
        "Hace cuatro dias estamos sin alumbrado publico en calle "
        "Sarmiento. Ya llamamos varias veces y nadie vino.",
    ),
    (
        "false",
        "Chicos, este sabado a las 9 nos juntamos a limpiar el "
        "baldio de la esquina. Traigan bolsas y guantes.",
    ),
    (
        "false",
        "Vendo heladera con freezer, funciona perfecto. "
        "Interesados por privado.",
    ),
]


def probar() -> None:

    print("=" * 60)
    print(info())
    print("=" * 60)

    sistema = (
        "Sos un clasificador de reclamos vecinales de un municipio "
        "argentino.\n\n"
        "Es RECLAMO cuando hay un problema que le corresponde "
        "resolver al municipio: falla de un servicio, problema del "
        "espacio publico, pedido de reparacion.\n\n"
        "NO es reclamo una venta, un saludo, una busqueda laboral, "
        "una noticia compartida, ni una convocatoria vecinal para "
        "resolver algo por cuenta propia.\n\n"
        "Respondé unicamente con el JSON pedido."
    )

    aciertos = 0

    for esperado, texto in CASOS:

        print(f"\nEsperado: es_reclamo = {esperado}")
        print(f"Texto   : {texto[:70]}...")

        try:
            contenido = completar(
                sistema,
                f"Publicacion:\n{texto}",
                ESQUEMA_PRUEBA,
            )

            datos = extraer_json(contenido)
            obtenido = str(datos.get("es_reclamo")).lower()

            marca = "OK " if obtenido == esperado else "FALLA"

            if obtenido == esperado:
                aciertos += 1

            print(f"[{marca}] respondio: {obtenido}")
            print(f"        motivo   : {datos.get('motivo', '')[:90]}")

        except Exception as error:
            print(f"[ERROR] {error}")

    print("\n" + "=" * 60)
    print(f"Aciertos: {aciertos}/{len(CASOS)}")
    print(contador.resumen())
    print("=" * 60)


if __name__ == "__main__":
    probar()
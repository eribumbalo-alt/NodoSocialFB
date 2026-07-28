from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from ollama import Client
from pydantic import BaseModel, Field, ValidationError


# ==========================
# RUTAS
# ==========================

BASE_DIR = Path(__file__).resolve().parent.parent

KNOWLEDGE_DIR = BASE_DIR / "knowledge"

ARCHIVO_PROMPT = BASE_DIR / "prompts" / "clasificar_reclamo.txt"
ARCHIVO_MEMORIA = KNOWLEDGE_DIR / "memoria_clasificador.json"
ARCHIVO_CATEGORIAS = KNOWLEDGE_DIR / "categorias.json"

MODELO = "llama3.2:3b"

cliente = Client(host="http://localhost:11434")


# ==========================
# MODELO DE RESPUESTA
# ==========================

class ClasificacionReclamo(BaseModel):

    es_reclamo: bool

    categoria: Literal[
        "Alumbrado público",
        "Higiene urbana",
        "Agua y cloacas",
        "Calles y baches",
        "Arbolado y poda",
        "Tránsito y señalización",
        "Seguridad",
        "Transporte",
        "Espacios públicos",
        "Animales",
        "Salud",
        "Educación",
        "Ruidos molestos",
        "Obras públicas",
        "Servicios públicos",
        "Conflicto vecinal",
        "Otro",
        "No corresponde",
    ]

    subcategoria: str

    urgencia: Literal[
        "Baja",
        "Media",
        "Alta",
        "Crítica",
    ]

    confianza: float = Field(ge=0, le=1)

    resumen: str
    motivo: str
    area_sugerida: str
    ubicacion: str


# ==========================
# CARGA DE ARCHIVOS
# ==========================

def cargar_prompt():

    return ARCHIVO_PROMPT.read_text(
        encoding="utf-8"
    )


def cargar_memoria():

    if not ARCHIVO_MEMORIA.exists():
        return []

    with open(
        ARCHIVO_MEMORIA,
        encoding="utf-8",
    ) as archivo:

        memoria = json.load(archivo)

    return memoria.get(
        "ejemplos",
        [],
    )


def cargar_categorias():

    with open(
        ARCHIVO_CATEGORIAS,
        encoding="utf-8",
    ) as archivo:

        return json.load(archivo)


# ==========================
# CONTEXTO IA
# ==========================

def construir_contexto():

    ejemplos = cargar_memoria()

    if not ejemplos:
        return ""

    texto = (
        "Ejemplos reales ya corregidos por un operador humano.\n"
        "Aprendé de estos ejemplos.\n\n"
    )

    for ejemplo in ejemplos[-8:]:

        texto += f"""
        
PUBLICACIÓN
{ejemplo["texto"]}

RESULTADO CORRECTO

es_reclamo={ejemplo["es_reclamo"]}
categoria={ejemplo["categoria"]}

----------------------------

"""

    return texto


def construir_categorias():

    categorias = cargar_categorias()

    texto = (
        "Categorías permitidas:\n\n"
    )

    for categoria, datos in categorias.items():

        texto += f"{categoria}\n"

        for sub in datos["subcategorias"]:

            texto += f"   - {sub}\n"

        texto += "\n"

    return texto


# ==========================
# CLASIFICADOR
# ==========================

def clasificar_publicacion(texto: str):

    texto = texto.strip()

    if not texto:
        raise ValueError(
            "Texto vacío."
        )

    prompt = cargar_prompt()

    contexto = construir_contexto()

    categorias = construir_categorias()

    prompt_sistema = f"""
{prompt}

{categorias}

{contexto}

# Memoria aprendida
contexto_memoria = construir_contexto()

# Categorías aprendidas
categorias = construir_categorias()

"""   

    prompt_usuario = f"""
Sos el clasificador inteligente del Nodo Social.

Antes de responder analizá los ejemplos ya validados por un operador humano.

==========================
EJEMPLOS APRENDIDOS
==========================

==========================
CATEGORÍAS DISPONIBLES
==========================

{categorias}

==========================
PUBLICACIÓN NUEVA
==========================

{texto}

==========================
REGLAS
==========================

No inventes información.

No inventes ubicaciones.

Si la publicación es:

- compra
- venta
- publicidad
- búsqueda laboral
- alquiler
- saludo
- recomendación
- evento
- consulta general

entonces

es_reclamo = false

categoria = "No corresponde"

subcategoria = "No corresponde"

urgencia = "Baja"

area_sugerida = "No corresponde"

Si existe una queja,
una denuncia,
un pedido de reparación,
un pedido al municipio,
una falla de servicio,
un problema urbano,
un problema ambiental,
un problema vial,
un problema de seguridad,
o un pedido concreto de solución,

entonces

es_reclamo = true

Usá los ejemplos aprendidos como referencia para decidir.
"""

    respuesta = cliente.chat(
        model=MODELO,
        messages=[
            {
                "role": "system",
                "content": prompt_sistema,
            },
            {
                "role": "user",
                "content": prompt_usuario,
            },
        ],
        format=ClasificacionReclamo.model_json_schema(),
        options={
            "temperature": 0,
        },
    )

    contenido = respuesta.message.content.strip()

    if not contenido:
        raise RuntimeError(
            "Ollama respondió vacío."
        )

    try:

        datos = json.loads(contenido)

        resultado = ClasificacionReclamo.model_validate(
            datos
        )

    except json.JSONDecodeError:

        raise RuntimeError(
            contenido
        )

    except ValidationError:

        raise RuntimeError(
            contenido
        )

    return resultado.model_dump()


# ==========================
# TEST
# ==========================

def mostrar(resultado):

    print(
        json.dumps(
            resultado,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":

    texto = """
Hace cuatro días estamos sin alumbrado público
en calle Sarmiento.
Ya llamamos varias veces y nadie vino.
"""

    resultado = clasificar_publicacion(texto)

    mostrar(resultado)
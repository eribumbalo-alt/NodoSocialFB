from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from ollama import Client
from pydantic import BaseModel, Field, ValidationError


# ==========================
# RUTAS Y CONFIGURACION
# ==========================

BASE_DIR = Path(__file__).resolve().parent.parent

KNOWLEDGE_DIR = BASE_DIR / "knowledge"

ARCHIVO_PROMPT = BASE_DIR / "prompts" / "clasificar_reclamo.txt"
ARCHIVO_MEMORIA = KNOWLEDGE_DIR / "memoria_clasificador.json"
ARCHIVO_CATEGORIAS = KNOWLEDGE_DIR / "categorias.json"

MODELO = "llama3.2:3b"

# Cuantos ejemplos de la memoria se meten en el prompt.
# Con llama3.2:3b no conviene pasar de 10: mas ejemplos empeoran el
# resultado en vez de mejorarlo.
CANTIDAD_EJEMPLOS = 8

# Claves que cada ejemplo de la memoria tiene que tener para ser usable.
CLAVES_REQUERIDAS = ("texto", "es_reclamo", "categoria")

cliente = Client(host="http://localhost:11434")


# ==========================
# REGLAS DE DECISION
# ==========================
# Este bloque se manda tal cual al modelo.
# Es el lugar donde vas a agregar aprendizajes cuando detectes
# errores repetidos. Editalo aca, no en medio del codigo.

REGLAS = """
==========================
REGLAS DE DECISION
==========================

No inventes informacion.

No inventes ubicaciones. Si la publicacion no menciona una calle, un
barrio o un lugar concreto, dejá el campo ubicacion vacio.

NO es un reclamo (es_reclamo = false) cuando la publicacion es:
- compra, venta o publicidad
- busqueda u oferta laboral
- alquiler o venta de inmuebles
- saludo, felicitacion o mensaje social
- pedido de recomendacion
- difusion de un evento
- consulta general
- una noticia compartida sobre un problema, sin reclamo propio
- una convocatoria vecinal para resolver algo por cuenta propia

En todos esos casos la respuesta debe ser:
es_reclamo = false
categoria = "No corresponde"
subcategoria = "No corresponde"
area_sugerida = "No corresponde"
urgencia = "Baja"

SI es un reclamo (es_reclamo = true) cuando hay:
- una queja o denuncia sobre un servicio o sobre el espacio publico
- un pedido de reparacion o de intervencion del municipio
- una falla de servicio (agua, luz, cloacas, recoleccion)
- un problema urbano, ambiental, vial o de seguridad
- un pedido concreto de solucion

Un reclamo puede estar formulado como pregunta
("¿alguien va a arreglar esto alguna vez?") o como simple descripcion
del problema, sin pedido explicito.
"""


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

def cargar_prompt() -> str:
    """Lee el prompt base desde prompts/clasificar_reclamo.txt"""

    if not ARCHIVO_PROMPT.exists():
        raise FileNotFoundError(
            f"No se encontro el prompt base: {ARCHIVO_PROMPT}"
        )

    return ARCHIVO_PROMPT.read_text(encoding="utf-8")


def cargar_memoria() -> list[dict]:
    """Lee la lista de ejemplos de memoria_clasificador.json"""

    if not ARCHIVO_MEMORIA.exists():
        print(
            f"[AVISO] No existe {ARCHIVO_MEMORIA}. "
            "Se clasifica sin ejemplos aprendidos."
        )
        return []

    with open(ARCHIVO_MEMORIA, encoding="utf-8") as archivo:
        memoria = json.load(archivo)

    return memoria.get("ejemplos", [])


def cargar_categorias() -> dict:
    """Lee la taxonomia desde categorias.json"""

    if not ARCHIVO_CATEGORIAS.exists():
        raise FileNotFoundError(
            f"No se encontro el archivo de categorias: "
            f"{ARCHIVO_CATEGORIAS}"
        )

    with open(ARCHIVO_CATEGORIAS, encoding="utf-8") as archivo:
        return json.load(archivo)


# ==========================
# CONTEXTO PARA LA IA
# ==========================

def ejemplos_utilizables(ejemplos: list) -> list[dict]:
    """Se queda solo con los ejemplos que tienen las claves esperadas.

    Si el archivo de memoria tiene otro formato, avisa por pantalla
    en vez de romper el programa.
    """

    validos = []
    descartados = 0

    for ejemplo in ejemplos:

        if not isinstance(ejemplo, dict):
            descartados += 1
            continue

        if all(clave in ejemplo for clave in CLAVES_REQUERIDAS):
            validos.append(ejemplo)
        else:
            descartados += 1

    if descartados:
        print(
            f"[AVISO] Se ignoraron {descartados} ejemplos de la memoria "
            f"porque no tienen las claves {CLAVES_REQUERIDAS}. "
            "Revisá el formato que genera entrenador.py."
        )

    return validos


def construir_contexto() -> str:
    """Arma el bloque de ejemplos que se le muestra al modelo.

    Devuelve texto vacio si no hay ejemplos utilizables.
    """

    ejemplos = ejemplos_utilizables(cargar_memoria())

    if not ejemplos:
        return ""

    # Por ahora se toman los ultimos N.
    # Mas adelante conviene elegirlos de forma estratificada:
    # unos pocos por categoria, y priorizando los errores corregidos.
    seleccion = ejemplos[-CANTIDAD_EJEMPLOS:]

    bloques = []

    for ejemplo in seleccion:

        es_reclamo = str(ejemplo["es_reclamo"]).lower()

        bloques.append(
            "PUBLICACION:\n"
            f"{str(ejemplo['texto']).strip()}\n\n"
            "RESULTADO CORRECTO:\n"
            f"es_reclamo = {es_reclamo}\n"
            f"categoria = {ejemplo['categoria']}"
        )

    return "\n\n------------------------------\n\n".join(bloques)


def construir_categorias() -> str:
    """Arma el listado de categorias y subcategorias permitidas."""

    categorias = cargar_categorias()

    texto = "==========================\n"
    texto += "CATEGORIAS PERMITIDAS\n"
    texto += "==========================\n\n"

    for categoria, datos in categorias.items():

        texto += f"{categoria}\n"

        for sub in datos["subcategorias"]:
            texto += f"   - {sub}\n"

        texto += "\n"

    return texto


def construir_prompts(texto: str) -> tuple[str, str]:
    """Devuelve (prompt_sistema, prompt_usuario).

    Se separa del clasificador para poder inspeccionar el prompt
    sin llamar a Ollama. Ver la funcion ver_prompt().
    """

    prompt_base = cargar_prompt()
    categorias = construir_categorias()
    contexto = construir_contexto()

    prompt_sistema = (
        f"{prompt_base}\n\n"
        f"{categorias}\n"
        f"{REGLAS}"
    )

    # El bloque de ejemplos solo aparece si realmente hay ejemplos.
    # Poner el titulo sin contenido confunde al modelo.
    if contexto:
        bloque_ejemplos = (
            "==========================\n"
            "EJEMPLOS VALIDADOS POR UN OPERADOR HUMANO\n"
            "==========================\n\n"
            "Estos casos ya fueron corregidos por una persona.\n"
            "Usalos como referencia para decidir.\n\n"
            f"{contexto}\n\n"
        )
    else:
        bloque_ejemplos = ""

    prompt_usuario = (
        f"{bloque_ejemplos}"
        "==========================\n"
        "PUBLICACION A CLASIFICAR\n"
        "==========================\n\n"
        f"{texto}\n\n"
        "Respondé unicamente con el JSON solicitado."
    )

    return prompt_sistema, prompt_usuario


# ==========================
# CLASIFICADOR
# ==========================

def clasificar_publicacion(texto: str) -> dict:
    """Clasifica una publicacion y devuelve un diccionario."""

    texto = texto.strip()

    if not texto:
        raise ValueError("Texto vacio.")

    prompt_sistema, prompt_usuario = construir_prompts(texto)

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
        raise RuntimeError("Ollama respondio vacio.")

    try:
        datos = json.loads(contenido)
        resultado = ClasificacionReclamo.model_validate(datos)

    except json.JSONDecodeError:
        raise RuntimeError(
            f"Ollama no devolvio un JSON valido:\n{contenido}"
        )

    except ValidationError as error:
        raise RuntimeError(
            f"El JSON no cumple el formato esperado.\n"
            f"Respuesta: {contenido}\n"
            f"Detalle: {error}"
        )

    return resultado.model_dump()


# ==========================
# HERRAMIENTAS DE DIAGNOSTICO
# ==========================

def diagnostico() -> None:
    """Muestra el estado de la memoria antes de clasificar."""

    print("=" * 60)
    print("DIAGNOSTICO DE CARGA")
    print("=" * 60)

    ejemplos = cargar_memoria()
    validos = ejemplos_utilizables(ejemplos)

    print(f"Ejemplos en el archivo : {len(ejemplos)}")
    print(f"Ejemplos utilizables   : {len(validos)}")
    print(
        f"Ejemplos en el prompt  : "
        f"{min(len(validos), CANTIDAD_EJEMPLOS)}"
    )

    if validos:
        print("\nPrimer ejemplo utilizable:")
        print(json.dumps(validos[0], ensure_ascii=False, indent=2))

    elif ejemplos:
        print("\nEl archivo tiene ejemplos pero con otro formato.")
        print("Primer ejemplo encontrado:")
        print(json.dumps(ejemplos[0], ensure_ascii=False, indent=2))

    print()


def ver_prompt(texto: str) -> None:
    """Imprime el prompt exacto que se le manda al modelo.

    Sirve para revisar que los ejemplos y las categorias esten
    realmente entrando. No llama a Ollama.
    """

    prompt_sistema, prompt_usuario = construir_prompts(texto)

    print("=" * 60)
    print("PROMPT DE SISTEMA")
    print("=" * 60)
    print(prompt_sistema)

    print("=" * 60)
    print("PROMPT DE USUARIO")
    print("=" * 60)
    print(prompt_usuario)


def mostrar(resultado: dict) -> None:

    print(
        json.dumps(
            resultado,
            ensure_ascii=False,
            indent=2,
        )
    )


# ==========================
# PRUEBA
# ==========================

PRUEBAS = [
    (
        "Deberia ser RECLAMO",
        "Hace cuatro dias estamos sin alumbrado publico en calle "
        "Sarmiento. Ya llamamos varias veces y nadie vino.",
    ),
    (
        "NO deberia ser reclamo",
        "Vendo heladera con freezer, funciona perfecto. "
        "Interesados por privado.",
    ),
    (
        "NO deberia ser reclamo (caso dificil)",
        "Chicos, este sabado a las 9 nos juntamos a limpiar el baldio "
        "de la esquina. Traigan bolsas y guantes.",
    ),
]


if __name__ == "__main__":

    diagnostico()

    for etiqueta, publicacion in PRUEBAS:

        print("=" * 60)
        print(etiqueta)
        print("=" * 60)
        print(publicacion)
        print("-" * 60)

        try:
            mostrar(clasificar_publicacion(publicacion))
        except Exception as error:
            print(f"ERROR: {error}")

        print()
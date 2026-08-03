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

# Con llama3.2:3b no conviene pasar de 10 ejemplos:
# mas ejemplos empeoran el resultado en vez de mejorarlo.
CANTIDAD_EJEMPLOS = 8

# Cuanto texto de la publicacion padre se usa como contexto
# al clasificar un comentario.
LIMITE_CONTEXTO = 700

CLAVES_REQUERIDAS = ("texto", "es_reclamo", "categoria")

cliente = Client(host="http://localhost:11434")


# ==========================
# REGLAS DE DECISION
# ==========================
# Este bloque se manda tal cual al modelo.
# Es el lugar donde agregar aprendizajes cuando detectes
# errores repetidos. Editalo aca, no en medio del codigo.

REGLAS = """
==========================
REGLAS DE DECISION
==========================

No inventes informacion.

No inventes ubicaciones. Si el texto no menciona una calle, un barrio
o un lugar concreto, dejá el campo ubicacion vacio.

NO es un reclamo (es_reclamo = false) cuando el texto es:
- compra, venta o publicidad
- busqueda u oferta laboral
- alquiler o venta de inmuebles
- saludo, felicitacion o mensaje social
- pedido de recomendacion
- difusion de un evento
- consulta general
- una noticia compartida sobre un problema, sin reclamo propio
- una convocatoria vecinal para resolver algo por cuenta propia
- un fenomeno natural que el municipio no puede reparar
  (un temblor, una tormenta, el calor)

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

La pregunta clave es siempre la misma:
¿hay algo concreto que el municipio pueda hacer al respecto?
Si la respuesta es no, no es un reclamo.
"""


REGLAS_COMENTARIO = """
==========================
ATENCION: ESTAS CLASIFICANDO UN COMENTARIO
==========================

El texto a clasificar es un COMENTARIO dentro de una publicacion.
Mas abajo vas a ver la publicacion original, que sirve solo como
contexto para entender de que se esta hablando.

Clasifica UNICAMENTE el comentario.
NO clasifiques la publicacion original.

NO es reclamo un comentario que solamente:
- adhiere sin aportar nada nuevo ("a mi tambien", "+1", "tal cual",
  "totalmente de acuerdo", "lo mismo digo")
- agradece, saluda o hace un chiste
- opina sobre politica, sobre el gobierno o sobre otra persona
- responde una pregunta de otro vecino
- etiqueta o menciona a alguien

SI es reclamo un comentario que aporta un problema propio con algun
dato nuevo: una ubicacion, una fecha, una duracion o un detalle
concreto.

Ejemplo que SI es reclamo:
"a mi me pasa lo mismo en San Martin al 300, hace tres semanas que
estamos sin luz"

Ejemplo que NO es reclamo:
"a mi tambien me pasa, es un desastre"
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

    if not ARCHIVO_PROMPT.exists():
        raise FileNotFoundError(
            f"No se encontro el prompt base: {ARCHIVO_PROMPT}"
        )

    return ARCHIVO_PROMPT.read_text(encoding="utf-8")


def cargar_memoria() -> list[dict]:

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
    """Se queda solo con los ejemplos que tienen las claves esperadas."""

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
            f"porque no tienen las claves {CLAVES_REQUERIDAS}."
        )

    return validos


def construir_contexto() -> str:
    """Arma el bloque de ejemplos aprendidos."""

    ejemplos = ejemplos_utilizables(cargar_memoria())

    if not ejemplos:
        return ""

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


def construir_prompts(
    texto: str,
    contexto_padre: str = "",
    tipo: str = "publicacion",
) -> tuple[str, str]:
    """Devuelve (prompt_sistema, prompt_usuario).

    tipo:
        "publicacion" -> se clasifica el texto tal cual
        "comentario"  -> se agrega la publicacion padre como contexto
    """

    prompt_base = cargar_prompt()
    categorias = construir_categorias()
    ejemplos = construir_contexto()

    es_comentario = tipo == "comentario"

    prompt_sistema = (
        f"{prompt_base}\n\n"
        f"{categorias}\n"
        f"{REGLAS}"
    )

    if es_comentario:
        prompt_sistema += f"\n{REGLAS_COMENTARIO}"

    # Los ejemplos solo aparecen si realmente existen.
    # Poner el titulo sin contenido confunde al modelo.
    if ejemplos:
        bloque_ejemplos = (
            "==========================\n"
            "EJEMPLOS VALIDADOS POR UN OPERADOR HUMANO\n"
            "==========================\n\n"
            "Estos casos ya fueron corregidos por una persona.\n"
            "Usalos como referencia para decidir.\n\n"
            f"{ejemplos}\n\n"
        )
    else:
        bloque_ejemplos = ""

    # Contexto del post padre, solo para comentarios.
    if es_comentario and contexto_padre.strip():
        bloque_contexto = (
            "==========================\n"
            "PUBLICACION ORIGINAL (SOLO CONTEXTO - NO CLASIFICAR)\n"
            "==========================\n\n"
            f"{contexto_padre.strip()[:LIMITE_CONTEXTO]}\n\n"
        )
        titulo_objetivo = "COMENTARIO A CLASIFICAR"

    else:
        bloque_contexto = ""
        titulo_objetivo = "PUBLICACION A CLASIFICAR"

    prompt_usuario = (
        f"{bloque_ejemplos}"
        f"{bloque_contexto}"
        "==========================\n"
        f"{titulo_objetivo}\n"
        "==========================\n\n"
        f"{texto}\n\n"
        "Respondé unicamente con el JSON solicitado."
    )

    return prompt_sistema, prompt_usuario


# ==========================
# CLASIFICADOR
# ==========================

def clasificar_publicacion(
    texto: str,
    contexto_padre: str = "",
    tipo: str = "publicacion",
) -> dict:
    """Clasifica un texto y devuelve un diccionario.

    Uso normal:
        clasificar_publicacion(texto_del_post)

    Para un comentario:
        clasificar_publicacion(
            texto_del_comentario,
            contexto_padre=texto_del_post,
            tipo="comentario",
        )
    """

    texto = texto.strip()

    if not texto:
        raise ValueError("Texto vacio.")

    prompt_sistema, prompt_usuario = construir_prompts(
        texto,
        contexto_padre,
        tipo,
    )

    respuesta = cliente.chat(
        model=MODELO,
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario},
        ],
        format=ClasificacionReclamo.model_json_schema(),
        options={"temperature": 0},
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
        print(json.dumps(ejemplos[0], ensure_ascii=False, indent=2))

    print()


def ver_prompt(
    texto: str,
    contexto_padre: str = "",
    tipo: str = "publicacion",
) -> None:
    """Imprime el prompt exacto que se le manda al modelo.

    No llama a Ollama. Sirve para revisar que los ejemplos,
    las categorias y el contexto esten entrando bien.
    """

    prompt_sistema, prompt_usuario = construir_prompts(
        texto,
        contexto_padre,
        tipo,
    )

    print("=" * 60)
    print("PROMPT DE SISTEMA")
    print("=" * 60)
    print(prompt_sistema)

    print("=" * 60)
    print("PROMPT DE USUARIO")
    print("=" * 60)
    print(prompt_usuario)


def mostrar(resultado: dict) -> None:

    print(json.dumps(resultado, ensure_ascii=False, indent=2))


# ==========================
# PRUEBA
# ==========================

POST_ALUMBRADO = (
    "Hace cuatro dias estamos sin alumbrado publico en calle "
    "Sarmiento. Ya llamamos varias veces y nadie vino."
)

PRUEBAS = [
    {
        "etiqueta": "PUBLICACION - deberia ser RECLAMO",
        "texto": POST_ALUMBRADO,
        "contexto": "",
        "tipo": "publicacion",
    },
    {
        "etiqueta": "PUBLICACION - NO deberia ser reclamo",
        "texto": (
            "Vendo heladera con freezer, funciona perfecto. "
            "Interesados por privado."
        ),
        "contexto": "",
        "tipo": "publicacion",
    },
    {
        "etiqueta": "PUBLICACION - NO deberia ser reclamo (dificil)",
        "texto": (
            "Chicos, este sabado a las 9 nos juntamos a limpiar el "
            "baldio de la esquina. Traigan bolsas y guantes."
        ),
        "contexto": "",
        "tipo": "publicacion",
    },
    {
        "etiqueta": "COMENTARIO - NO deberia ser reclamo (adhesion vacia)",
        "texto": "A mi tambien me pasa, es un desastre",
        "contexto": POST_ALUMBRADO,
        "tipo": "comentario",
    },
    {
        "etiqueta": "COMENTARIO - SI deberia ser reclamo (aporta datos)",
        "texto": (
            "Igual aca en San Martin al 300, hace tres semanas que "
            "estamos sin luz en toda la cuadra"
        ),
        "contexto": POST_ALUMBRADO,
        "tipo": "comentario",
    },
]


if __name__ == "__main__":

    diagnostico()

    for prueba in PRUEBAS:

        print("=" * 60)
        print(prueba["etiqueta"])
        print("=" * 60)
        print(prueba["texto"])
        print("-" * 60)

        try:
            mostrar(
                clasificar_publicacion(
                    prueba["texto"],
                    contexto_padre=prueba["contexto"],
                    tipo=prueba["tipo"],
                )
            )
        except Exception as error:
            print(f"ERROR: {error}")

        print()
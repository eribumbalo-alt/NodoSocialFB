from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.sync_api import Page, sync_playwright

from clasificador_ia import clasificar_publicacion
from guardar_sheet import (
    guardar_reclamos_sheet,
    guardar_dataset_ia,
)

BASE_DIR = Path(__file__).resolve().parent.parent

ARCHIVO_GRUPOS = BASE_DIR / "config" / "grupos.txt"
CARPETA_PERFIL = BASE_DIR / "perfil_facebook_nodo"
CARPETA_DATOS = BASE_DIR / "data"

CANTIDAD_SCROLLS = 8
ESPERA_INICIAL_MS = 10000
ESPERA_ENTRE_SCROLLS_MS = 2500

LIMITE_TEXTO_IA = 3000

# ----------------------------------------------------------
# CONTROL DE VOLUMEN
# ----------------------------------------------------------
# Cada comentario es una llamada mas a Ollama.

ANALIZAR_COMENTARIOS = True
MAXIMO_COMENTARIOS_POR_POST = 12

LARGO_MINIMO_PUBLICACION = 80
MINIMO_PALABRAS_PUBLICACION = 12

LARGO_MINIMO_COMENTARIO = 45
MINIMO_PALABRAS_COMENTARIO = 8

# Cuantas pasadas de clic se hacen para abrir textos y comentarios.
PASADAS_EXPANSION = 3


# ==========================================================
# LIMPIEZA DE TEXTO
# ==========================================================

LINEAS_RUIDO = {
    "me gusta",
    "comentar",
    "compartir",
    "enviar",
    "responder",
    "ver mas",
    "ver más",
    "ver menos",
    "ver traduccion",
    "ver traducción",
    "editado",
    "seguir",
    "siguiendo",
    "unirte al grupo",
    "todos los comentarios",
    "comentarios mas relevantes",
    "comentarios más relevantes",
    "mas relevantes",
    "más relevantes",
    "escribe un comentario...",
    "autor",
    "administrador",
    "moderador",
    "colaborador en ascenso",
    "like",
    "reply",
    "share",
    "see more",
}

PATRON_TIEMPO = re.compile(
    r"^\s*(hace\s+)?\d+\s*"
    r"(min|minutos?|h|horas?|d|d[ií]as?|sem|semanas?|años?)\s*$",
    re.IGNORECASE,
)

PATRON_SOLO_SIMBOLOS = re.compile(r"^[\s·•\-–—\d,.]*$")

PATRON_RESPUESTAS = re.compile(
    r"^\s*(ver\s+)?\d+\s+respuestas?\s*$",
    re.IGNORECASE,
)

# ----------------------------------------------------------
# ENCABEZADO DE AUTOR
# ----------------------------------------------------------
# Facebook pega el nombre y la hora al comienzo del texto, sin
# salto de linea:
#
#     "Dayi Diaz  · 7 hYo si lo senti aca en maipu..."
#     "· 3 hyo nolo centi porque..."
#     "Juana Grimal  · 4 dias  · Colaborador en ascensoY como..."
#
# Por eso hay que sacarlo con un patron sobre el comienzo del
# texto y no linea por linea.

INSIGNIAS = (
    "Colaborador en ascenso",
    "Colaborador destacado",
    "Contribuyente principal",
    "Miembro destacado",
    "Administrador",
    "Moderador",
    "Autor",
    "Editado",
)

_INSIGNIAS_RE = "|".join(re.escape(i) for i in INSIGNIAS)

PATRON_ENCABEZADO = re.compile(
    r"^\s*"
    r"(?P<autor>[^·\n]{0,60}?)"
    r"\s*·\s*"
    r"\d+\s*"
    r"(?:minutos?|min|horas?|semanas?|sem|d[ií]as?|años?|h|d)"
    r"(?:\s*·\s*(?:" + _INSIGNIAS_RE + r"))*",
    re.IGNORECASE,
)


def quitar_encabezado(texto: str) -> tuple[str, str]:
    """Saca 'Nombre · 7 h · Insignia' del comienzo.

    Devuelve (texto_sin_encabezado, nombre_del_autor).
    El nombre no se guarda: se usa para poder limpiar las
    menciones a esa persona en otros comentarios.
    """

    if not texto:
        return "", ""

    coincidencia = PATRON_ENCABEZADO.match(texto)

    if not coincidencia:
        return texto, ""

    autor = (coincidencia.group("autor") or "").strip()
    resto = texto[coincidencia.end():].lstrip(" ·\t\n")

    return resto, autor


def quitar_mencion(texto: str, autores: set[str]) -> str:
    """Saca el nombre de otra persona cuando abre una respuesta."""

    for nombre in sorted(autores, key=len, reverse=True):

        if len(nombre) < 5:
            continue

        if texto.startswith(nombre):
            return texto[len(nombre):].lstrip(" ,:\n")

    return texto


def limpiar_lineas(texto: str) -> str:
    """Saca las lineas que son interfaz y no contenido."""

    if not texto:
        return ""

    lineas_limpias = []

    for linea in texto.splitlines():

        linea = re.sub(r"[ \t]+", " ", linea).strip()

        if not linea:
            continue

        if linea.lower() in LINEAS_RUIDO:
            continue

        if PATRON_TIEMPO.match(linea):
            continue

        if PATRON_SOLO_SIMBOLOS.match(linea):
            continue

        if PATRON_RESPUESTAS.match(linea):
            continue

        lineas_limpias.append(linea)

    texto = "\n".join(lineas_limpias)
    texto = re.sub(r"\n{3,}", "\n\n", texto)

    return texto.strip()


def motivo_descarte(texto: str, tipo: str, tiene_contexto: bool) -> str:
    """Devuelve '' si la captura sirve, o el motivo del descarte."""

    if tipo == "comentario" and tiene_contexto:
        largo_minimo = LARGO_MINIMO_COMENTARIO
        palabras_minimas = MINIMO_PALABRAS_COMENTARIO
    else:
        # Un comentario sin su publicacion de contexto tiene que
        # sostenerse solo, asi que se le pide lo mismo que a un post.
        largo_minimo = LARGO_MINIMO_PUBLICACION
        palabras_minimas = MINIMO_PALABRAS_PUBLICACION

    if not texto:
        return "texto vacio"

    if len(texto) < largo_minimo:
        return f"corto ({len(texto)} < {largo_minimo})"

    if len(texto.split()) < palabras_minimas:
        return f"pocas palabras ({len(texto.split())})"

    minuscula = texto.lower()

    for marca in ("responder", "me gusta", "compartir"):
        if minuscula.count(marca) >= 2:
            return f"ruido de interfaz ('{marca}' repetido)"

    return ""


# ==========================================================
# GRUPOS Y ENLACES
# ==========================================================

def cargar_grupos() -> list[dict[str, str]]:

    grupos = []

    with ARCHIVO_GRUPOS.open("r", encoding="utf-8") as archivo:

        for linea in archivo:

            linea = linea.strip()

            if not linea or "|" not in linea:
                continue

            nombre, url = linea.split("|", 1)

            grupos.append(
                {
                    "nombre": nombre.strip(),
                    "url": url.strip(),
                }
            )

    return grupos


PARAMETROS_UTILES = (
    "story_fbid",
    "id",
    "comment_id",
    "reply_comment_id",
)


def normalizar_link(link: str) -> str:

    if not link:
        return ""

    parsed = urlparse(link)
    parametros = parse_qs(parsed.query)

    permitidos = {}

    for nombre in PARAMETROS_UTILES:
        if nombre in parametros:
            permitidos[nombre] = parametros[nombre]

    query = urlencode(permitidos, doseq=True)

    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", query, "")
    )


def tipo_por_link(link: str) -> str:
    """Publicacion o comentario, decidido por la URL.

    Este es el criterio confiable: Facebook siempre pone
    comment_id en el enlace de un comentario y nunca en el
    de una publicacion. No depende de la estructura del HTML,
    que cambia seguido.
    """

    if "comment_id=" in link:
        return "comentario"

    return "publicacion"


PATRONES_ID = (
    re.compile(r"/posts/(\d+)"),
    re.compile(r"/permalink/(\d+)"),
    re.compile(r"story_fbid=(\d+)"),
)


def id_publicacion(link: str) -> str:
    """Saca el ID del post del enlace, para emparejar comentarios."""

    for patron in PATRONES_ID:
        coincidencia = patron.search(link)
        if coincidencia:
            return coincidencia.group(1)

    return ""


# ==========================================================
# NAVEGACION
# ==========================================================

def hacer_scroll(pagina: Page) -> None:

    for numero in range(CANTIDAD_SCROLLS):

        print(f"   Scroll {numero + 1}/{CANTIDAD_SCROLLS}")

        pagina.mouse.wheel(0, 1800)
        pagina.wait_for_timeout(ESPERA_ENTRE_SCROLLS_MS)


# El clic por nombre accesible de Playwright encontraba muy pocos
# botones. Hacerlo desde JavaScript es bastante mas confiable.
JS_CLIC = """
(patron) => {
    const re = new RegExp(patron, "i");
    let n = 0;

    for (const b of document.querySelectorAll('[role="button"]')) {

        const t = (b.innerText || "").trim();

        if (!t || t.length > 45) continue;

        if (re.test(t)) {
            try { b.click(); n++; } catch (e) {}
        }
    }

    return n;
}
"""

PATRON_VER_MAS = r"^ver m[áa]s$|^see more$"

PATRON_MAS_COMENTARIOS = (
    r"^ver m[áa]s comentarios|"
    r"^comentarios anteriores|"
    r"^ver \d+ respuestas?|"
    r"^\d+ respuestas?|"
    r"^view (more|previous) comments"
)


def clic_repetido(pagina: Page, patron: str, pasadas: int) -> int:
    """Hace varias pasadas: abrir un bloque revela otros."""

    total = 0

    for _ in range(pasadas):

        try:
            abiertos = pagina.evaluate(JS_CLIC, patron)

        except Exception:
            break

        if not abiertos:
            break

        total += abiertos
        pagina.wait_for_timeout(1200)

    return total


def expandir_todo(pagina: Page) -> tuple[int, int]:
    """Abre comentarios ocultos y despues los textos truncados."""

    comentarios = 0

    if ANALIZAR_COMENTARIOS:
        comentarios = clic_repetido(
            pagina,
            PATRON_MAS_COMENTARIOS,
            PASADAS_EXPANSION,
        )

    # Los textos se expanden despues, porque abrir comentarios
    # hace aparecer mas botones "Ver mas".
    textos = clic_repetido(
        pagina,
        PATRON_VER_MAS,
        PASADAS_EXPANSION,
    )

    return textos, comentarios


# ==========================================================
# EXTRACCION
# ==========================================================

JS_EXTRAER = """
() => {
    const PODAR =
        '[role="article"],' +
        '[role="button"],' +
        '[role="menu"],' +
        '[role="menuitem"],' +
        '[role="toolbar"],' +
        '[role="navigation"],' +
        '[role="complementary"],' +
        'form,' +
        'textarea';

    const textoPropio = (nodo) => {
        const clon = nodo.cloneNode(true);
        clon.querySelectorAll(PODAR).forEach((n) => n.remove());
        return clon.innerText || "";
    };

    const articulos = Array.from(
        document.querySelectorAll('[role="article"]')
    );

    const salida = [];

    for (const art of articulos) {

        const padre = art.parentElement;
        const anidado = !!(padre && padre.closest('[role="article"]'));

        const enlaces = Array.from(
            art.querySelectorAll(
                'a[href*="/posts/"],' +
                'a[href*="/permalink/"],' +
                'a[href*="story_fbid="]'
            )
        )
            .map((e) => e.href || "")
            .filter((h) => h);

        // Se prefiere un enlace SIN comment_id: ese es el
        // permalink de la publicacion.
        let link = "";
        const sinComentario = enlaces.find(
            (h) => h.indexOf("comment_id=") === -1
        );

        if (sinComentario) {
            link = sinComentario;
        } else if (enlaces.length > 0) {
            link = enlaces[0];
        }

        let texto = "";

        const mensaje = art.querySelector(
            '[data-ad-preview="message"],' +
            '[data-ad-comet-preview="message"]'
        );

        if (mensaje && mensaje.innerText.trim().length > 0) {
            texto = mensaje.innerText;
        } else {
            texto = textoPropio(art);
        }

        salida.push({
            link: link,
            texto: texto,
            anidado: anidado,
            cantidad_enlaces: enlaces.length,
        });
    }

    return salida;
}
"""


def analizar_articulos(pagina: Page) -> list[dict]:
    """Devuelve todos los articulos, ya limpios y clasificados.

    Cada item incluye el motivo del descarte cuando corresponde,
    para poder diagnosticar sin adivinar.
    """

    try:
        crudos = pagina.evaluate(JS_EXTRAER)

    except Exception as error:
        print(f"   [ERROR] No se pudo extraer: {error}")
        return []

    items = []
    autores: set[str] = set()

    # --- primera pasada: limpiar y detectar autores ---
    for crudo in crudos:

        link = normalizar_link(crudo.get("link", ""))

        texto, autor = quitar_encabezado(crudo.get("texto", ""))
        texto = limpiar_lineas(texto)

        if autor:
            autores.add(autor)

        items.append(
            {
                "link": link,
                "texto": texto,
                "tipo": tipo_por_link(link),
                "post_id": id_publicacion(link),
                "anidado": crudo.get("anidado", False),
                "autor": autor,
                "motivo": "",
            }
        )

    # --- segunda pasada: sacar menciones y evaluar ---
    contextos: dict[str, str] = {}

    for item in items:
        if item["tipo"] == "publicacion" and item["post_id"]:
            if item["texto"]:
                contextos[item["post_id"]] = item["texto"]

    for item in items:

        item["texto"] = quitar_mencion(item["texto"], autores)

        item["contexto_padre"] = (
            contextos.get(item["post_id"], "")
            if item["tipo"] == "comentario"
            else ""
        )

        if not item["link"]:
            item["motivo"] = "sin enlace"
            continue

        item["motivo"] = motivo_descarte(
            item["texto"],
            item["tipo"],
            bool(item["contexto_padre"]),
        )

    return items


def extraer_registros(pagina: Page) -> list[dict]:
    """Convierte los articulos validos en registros a clasificar."""

    items = analizar_articulos(pagina)

    registros = []
    links_vistos = set()
    por_post: dict[str, int] = {}

    for item in items:

        if item["motivo"]:
            continue

        if item["tipo"] == "comentario":

            if not ANALIZAR_COMENTARIOS:
                continue

            usados = por_post.get(item["post_id"], 0)

            if usados >= MAXIMO_COMENTARIOS_POR_POST:
                continue

            por_post[item["post_id"]] = usados + 1

        if item["link"] in links_vistos:
            continue

        links_vistos.add(item["link"])

        registros.append(
            {
                "tipo": item["tipo"],
                "texto": item["texto"],
                "link": item["link"],
                "contexto_padre": item["contexto_padre"],
            }
        )

    publicaciones = sum(
        1 for r in registros if r["tipo"] == "publicacion"
    )

    print(
        f"   Articulos: {len(items)} | "
        f"Publicaciones: {publicaciones} | "
        f"Comentarios: {len(registros) - publicaciones}"
    )

    return registros


# ==========================================================
# CLASIFICACION
# ==========================================================

def analizar_registro(grupo: str, registro: dict) -> dict:

    texto = registro["texto"][:LIMITE_TEXTO_IA]
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tipo = registro.get("tipo", "publicacion")

    base = {
        "fecha_captura": ahora,
        "grupo": grupo,
        "tipo": tipo,
        "texto": registro["texto"],
        "link": registro["link"],
    }

    try:
        resultado = clasificar_publicacion(
            texto,
            contexto_padre=registro.get("contexto_padre", ""),
            tipo=tipo,
        )

    except Exception as error:

        print(f"   [ERROR clasificando] {error}")

        return {
            **base,
            "es_reclamo": False,
            "respuesta_ia": "ERROR",
            "categoria": "",
            "subcategoria": "",
            "urgencia": "",
            "confianza": 0,
            "resumen": "",
            "motivo": str(error),
            "area_sugerida": "",
            "ubicacion": "",
        }

    es_reclamo = resultado.get("es_reclamo", False)

    return {
        **base,
        "es_reclamo": es_reclamo,
        "respuesta_ia": "Reclamo" if es_reclamo else "No Reclamo",
        "categoria": resultado.get("categoria", ""),
        "subcategoria": resultado.get("subcategoria", ""),
        "urgencia": resultado.get("urgencia", ""),
        "confianza": resultado.get("confianza", 0),
        "resumen": resultado.get("resumen", ""),
        "motivo": resultado.get("motivo", ""),
        "area_sugerida": resultado.get("area_sugerida", ""),
        "ubicacion": resultado.get("ubicacion", ""),
    }


# ==========================================================
# RECORRIDO
# ==========================================================

def abrir_navegador(p):

    return p.chromium.launch_persistent_context(
        user_data_dir=str(CARPETA_PERFIL),
        headless=False,
        viewport={"width": 1366, "height": 768},
    )


def preparar_grupo(pagina: Page, grupo: dict) -> None:

    print(f"\nGrupo: {grupo['nombre']}")

    pagina.goto(grupo["url"], wait_until="domcontentloaded")
    pagina.wait_for_timeout(ESPERA_INICIAL_MS)

    hacer_scroll(pagina)

    textos, comentarios = expandir_todo(pagina)

    print(f"   Textos expandidos     : {textos}")
    print(f"   Comentarios expandidos: {comentarios}")


# ==========================================================
# MODO PRUEBA
# ==========================================================

def modo_prueba() -> None:
    """Captura un grupo y muestra el diagnostico completo.

    NO llama a Ollama y NO escribe en Google Sheets.
    """

    grupos = cargar_grupos()

    if not grupos:
        print("No hay grupos en config/grupos.txt")
        return

    grupo = grupos[0]

    with sync_playwright() as p:

        contexto = abrir_navegador(p)

        pagina = (
            contexto.pages[0]
            if contexto.pages
            else contexto.new_page()
        )

        preparar_grupo(pagina, grupo)
        items = analizar_articulos(pagina)

        contexto.close()

    aceptados = [i for i in items if not i["motivo"]]
    descartados = [i for i in items if i["motivo"]]

    publicaciones = [
        i for i in aceptados if i["tipo"] == "publicacion"
    ]
    comentarios = [
        i for i in aceptados if i["tipo"] == "comentario"
    ]

    print("\n" + "=" * 70)
    print(f"ARTICULOS ENCONTRADOS : {len(items)}")
    print(f"   Aceptados          : {len(aceptados)}")
    print(f"      Publicaciones   : {len(publicaciones)}")
    print(f"      Comentarios     : {len(comentarios)}")
    print(f"   Descartados        : {len(descartados)}")
    print("=" * 70)

    # ---- por que se descarto cada uno ----
    if descartados:

        conteo: dict[str, int] = {}

        for item in descartados:
            clave = item["motivo"].split(" (")[0]
            conteo[clave] = conteo.get(clave, 0) + 1

        print("\nMOTIVOS DE DESCARTE:")

        for motivo, cantidad in sorted(
            conteo.items(),
            key=lambda par: par[1],
            reverse=True,
        ):
            print(f"   {cantidad:3}  {motivo}")

    # ---- muestra de descartados, para revisar ----
    print("\n" + "-" * 70)
    print("DESCARTADOS (primeros 8)")
    print("-" * 70)

    for item in descartados[:8]:

        resumen = " ".join(item["texto"].split())[:110]

        print(f"\n[{item['tipo']}] motivo: {item['motivo']}")
        print(f"   anidado: {item['anidado']}")
        print(f"   link   : {item['link'][:100] or '(vacio)'}")
        print(f"   texto  : {resumen or '(vacio)'}")

    # ---- muestra de aceptados ----
    print("\n" + "-" * 70)
    print("ACEPTADOS (primeros 10)")
    print("-" * 70)

    for item in aceptados[:10]:

        print(f"\n----- {item['tipo'].upper()} -----")
        print(f"Link : {item['link'][:110]}")
        print(f"Largo: {len(item['texto'])} caracteres")

        if item["tipo"] == "comentario":
            contexto_corto = " ".join(
                item["contexto_padre"].split()
            )[:90]
            print(f"Post : {contexto_corto or '(SIN CONTEXTO)'}")

        print("-" * 40)
        print(item["texto"][:400])

    # ---- archivo completo ----
    CARPETA_DATOS.mkdir(exist_ok=True)
    archivo = CARPETA_DATOS / "capturas_prueba.txt"

    with open(archivo, "w", encoding="utf-8") as salida:

        salida.write("=== ACEPTADOS ===\n\n")

        for numero, item in enumerate(aceptados, start=1):

            salida.write(
                f"----- {numero}. {item['tipo'].upper()} -----\n"
            )
            salida.write(f"{item['link']}\n\n")

            if item["contexto_padre"]:
                salida.write("[CONTEXTO DEL POST]\n")
                salida.write(f"{item['contexto_padre'][:300]}\n\n")

            salida.write(f"{item['texto']}\n\n\n")

        salida.write("\n\n=== DESCARTADOS ===\n\n")

        for numero, item in enumerate(descartados, start=1):

            salida.write(
                f"----- {numero}. {item['tipo'].upper()} "
                f"({item['motivo']}) -----\n"
            )
            salida.write(f"{item['link']}\n")
            salida.write(f"{item['texto'][:400]}\n\n")

    print(f"\n\nGuardado en: {archivo}")


# ==========================================================
# CICLO COMPLETO
# ==========================================================

def rastrear_grupos() -> None:

    grupos = cargar_grupos()

    reclamos_detectados = []
    dataset_ia = []

    with sync_playwright() as p:

        contexto = abrir_navegador(p)

        pagina = (
            contexto.pages[0]
            if contexto.pages
            else contexto.new_page()
        )

        for grupo in grupos:

            preparar_grupo(pagina, grupo)
            registros = extraer_registros(pagina)

            print(f"   Clasificando {len(registros)} registros...")

            for registro in registros:

                resultado = analizar_registro(
                    grupo["nombre"],
                    registro,
                )

                dataset_ia.append(resultado)

                if resultado["es_reclamo"]:

                    reclamos_detectados.append(resultado)

                    print(
                        f"   ✔ Reclamo [{resultado['tipo']}]: "
                        f"{resultado['categoria']}"
                    )

        contexto.close()

    cantidad_dataset = guardar_dataset_ia(dataset_ia)
    cantidad_reclamos = guardar_reclamos_sheet(reclamos_detectados)

    desde_comentarios = sum(
        1 for r in reclamos_detectados if r["tipo"] == "comentario"
    )

    print("\n" + "=" * 45)
    print(f"Dataset IA           : {cantidad_dataset}")
    print(f"Reclamos detectados  : {len(reclamos_detectados)}")
    print(
        f"   en publicaciones  : "
        f"{len(reclamos_detectados) - desde_comentarios}"
    )
    print(f"   en comentarios    : {desde_comentarios}")
    print(f"Nuevos en Sheet      : {cantidad_reclamos}")
    print("=" * 45)


if __name__ == "__main__":

    if "--prueba" in sys.argv:
        modo_prueba()
    else:
        rastrear_grupos()
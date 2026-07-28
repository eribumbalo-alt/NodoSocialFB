from __future__ import annotations

import re
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

CANTIDAD_SCROLLS = 8
ESPERA_INICIAL_MS = 10000
ESPERA_ENTRE_SCROLLS_MS = 2500

LIMITE_TEXTO_IA = 3000


def cargar_grupos() -> list[dict[str, str]]:
    grupos = []

    with ARCHIVO_GRUPOS.open(
        "r",
        encoding="utf-8",
    ) as archivo:

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


def limpiar_texto(texto: str) -> str:

    texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto = re.sub(r"[ \t]+", " ", texto)

    return texto.strip()


def normalizar_link(link: str) -> str:

    parsed = urlparse(link)

    parametros = parse_qs(parsed.query)

    permitidos = {}

    for nombre in ("story_fbid", "id"):

        if nombre in parametros:
            permitidos[nombre] = parametros[nombre]

    query = urlencode(
        permitidos,
        doseq=True,
    )

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            "",
            query,
            "",
        )
    )


def hacer_scroll(pagina: Page):

    for numero in range(CANTIDAD_SCROLLS):

        print(
            f"Scroll {numero+1}/{CANTIDAD_SCROLLS}"
        )

        pagina.mouse.wheel(0, 1800)

        pagina.wait_for_timeout(
            ESPERA_ENTRE_SCROLLS_MS
        )


def extraer_publicaciones(
    pagina: Page,
) -> list[dict]:

    selector = (
        'a[href*="/posts/"],'
        'a[href*="/permalink/"],'
        'a[href*="story_fbid="]'
    )

    enlaces = pagina.locator(selector)

    publicaciones = []
    links_vistos = set()

    for i in range(enlaces.count()):

        enlace = enlaces.nth(i)

        try:

            datos = enlace.evaluate(
                """
                (e)=>{
                    const post=e.closest('[role="article"]');

                    return{
                        link:e.href || "",
                        texto:post ? post.innerText : ""
                    }
                }
                """
            )

        except Exception:
            continue

        texto = limpiar_texto(
            datos.get("texto", "")
        )

        link = normalizar_link(
            datos.get("link", "")
        )

        if not texto:
            continue

        if len(texto) < 25:
            continue

        if link in links_vistos:
            continue

        links_vistos.add(link)

        publicaciones.append(
            {
                "texto": texto,
                "link": link,
            }
        )

    return publicaciones


def analizar_publicacion(
    grupo: str,
    publicacion: dict,
) -> dict:

    texto = publicacion["texto"][:LIMITE_TEXTO_IA]

    try:

        resultado = clasificar_publicacion(texto)

    except Exception as error:

        print(error)

        return {
            "fecha_captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "grupo": grupo,
            "texto": publicacion["texto"],
            "link": publicacion["link"],
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

    es_reclamo = resultado.get(
        "es_reclamo",
        False,
    )

    return {
        "fecha_captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "grupo": grupo,
        "texto": publicacion["texto"],
        "link": publicacion["link"],
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


def rastrear_grupos():

    grupos = cargar_grupos()

    reclamos_detectados = []

    dataset_ia = []

    with sync_playwright() as p:

        contexto = p.chromium.launch_persistent_context(
            user_data_dir=str(CARPETA_PERFIL),
            headless=False,
            viewport={
                "width": 1366,
                "height": 768,
            },
        )

        pagina = (
            contexto.pages[0]
            if contexto.pages
            else contexto.new_page()
        )

        for grupo in grupos:

            print(f"\nGrupo: {grupo['nombre']}")

            pagina.goto(
                grupo["url"],
                wait_until="domcontentloaded",
            )

            pagina.wait_for_timeout(
                ESPERA_INICIAL_MS
            )

            hacer_scroll(pagina)

            publicaciones = extraer_publicaciones(
                pagina
            )

            print(
                f"Publicaciones: {len(publicaciones)}"
            )

            for publicacion in publicaciones:

                resultado = analizar_publicacion(
                    grupo["nombre"],
                    publicacion,
                )

                dataset_ia.append(resultado)

                if resultado["es_reclamo"]:

                    reclamos_detectados.append(
                        resultado
                    )

                    print(
                        f"✔ Reclamo: {resultado['categoria']}"
                    )

        contexto.close()

    cantidad_dataset = guardar_dataset_ia(
        dataset_ia
    )

    cantidad_reclamos = guardar_reclamos_sheet(
        reclamos_detectados
    )

    print("\n=============================")
    print(f"Dataset IA: {cantidad_dataset}")
    print(f"Reclamos IA: {len(reclamos_detectados)}")
    print(f"Nuevos en Sheet: {cantidad_reclamos}")
    print("=============================")


if __name__ == "__main__":
    rastrear_grupos()
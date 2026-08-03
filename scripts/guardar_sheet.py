from __future__ import annotations

from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials


BASE_DIR = Path(__file__).resolve().parent.parent

ARCHIVO_CREDENCIALES = (
    BASE_DIR / "config" / "credenciales_google.json"
)

NOMBRE_SPREADSHEET = "Nodo Social Reclamos"
NOMBRE_HOJA = "Reclamos"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# IMPORTANTE: "tipo" va al FINAL de la lista a proposito.
# La funcion obtener_links_existentes lee la columna 4 (link).
# Si se agregara una columna al principio, esa lectura se romperia.

COLUMNAS = [
    "fecha_captura",
    "grupo",
    "texto",
    "link",
    "categoria",
    "subcategoria",
    "urgencia",
    "confianza",
    "resumen",
    "motivo",
    "area_sugerida",
    "ubicacion",
    "tipo",
]

COLUMNAS_DATASET = [
    "fecha_captura",
    "grupo",
    "texto",
    "link",
    "respuesta_ia",
    "categoria_ia",
    "confianza",
    "decision_sistema",
    "validacion_humana",
    "observaciones",
    "tipo",
]

# Columna donde esta el link, para deduplicar.
COLUMNA_LINK = 4


def letra_columna(cantidad: int) -> str:
    """Convierte 13 en 'M', 11 en 'K', etc."""

    letra = ""

    while cantidad > 0:
        cantidad, resto = divmod(cantidad - 1, 26)
        letra = chr(65 + resto) + letra

    return letra


def conectar_google_sheet(nombre_hoja=NOMBRE_HOJA):
    """Conecta el proyecto con Google Sheets."""

    if not ARCHIVO_CREDENCIALES.exists():
        raise FileNotFoundError(
            f"No se encontraron las credenciales: "
            f"{ARCHIVO_CREDENCIALES}"
        )

    credenciales = Credentials.from_service_account_file(
        str(ARCHIVO_CREDENCIALES),
        scopes=SCOPES,
    )

    cliente = gspread.authorize(credenciales)
    spreadsheet = cliente.open(NOMBRE_SPREADSHEET)

    return spreadsheet.worksheet(nombre_hoja)


def preparar_encabezados(hoja, columnas: list[str]) -> None:
    """Crea o corrige la fila de encabezados."""

    primera_fila = hoja.row_values(1)

    if primera_fila != columnas:

        rango = f"A1:{letra_columna(len(columnas))}1"

        hoja.update(
            range_name=rango,
            values=[columnas],
        )


def obtener_links_existentes(hoja) -> set[str]:
    """Lee la columna link para evitar duplicados."""

    valores = hoja.col_values(COLUMNA_LINK)

    if valores and valores[0].strip().lower() == "link":
        valores = valores[1:]

    return {
        valor.strip()
        for valor in valores
        if valor.strip()
    }


def guardar_reclamos_sheet(reclamos: list[dict]) -> int:
    """Guarda unicamente reclamos nuevos."""

    if not reclamos:
        return 0

    hoja = conectar_google_sheet()
    preparar_encabezados(hoja, COLUMNAS)

    links_existentes = obtener_links_existentes(hoja)
    filas_nuevas: list[list] = []

    for reclamo in reclamos:

        link = str(reclamo.get("link", "")).strip()

        if not link or link in links_existentes:
            continue

        filas_nuevas.append(
            [
                reclamo.get("fecha_captura", ""),
                reclamo.get("grupo", ""),
                reclamo.get("texto", ""),
                link,
                reclamo.get("categoria", ""),
                reclamo.get("subcategoria", ""),
                reclamo.get("urgencia", ""),
                reclamo.get("confianza", ""),
                reclamo.get("resumen", ""),
                reclamo.get("motivo", ""),
                reclamo.get("area_sugerida", ""),
                reclamo.get("ubicacion", ""),
                reclamo.get("tipo", "publicacion"),
            ]
        )

        links_existentes.add(link)

    if filas_nuevas:
        hoja.append_rows(
            filas_nuevas,
            value_input_option="USER_ENTERED",
        )

    return len(filas_nuevas)


def guardar_dataset_ia(publicaciones: list[dict]) -> int:
    """Guarda todas las publicaciones y comentarios analizados.

    Deduplica por link igual que la hoja de reclamos: sin esto,
    cada corrida repetia las mismas filas y sobreponderaba
    publicaciones repetidas en el dataset de entrenamiento.
    """

    if not publicaciones:
        return 0

    hoja = conectar_google_sheet("Dataset IA")
    preparar_encabezados(hoja, COLUMNAS_DATASET)

    links_existentes = obtener_links_existentes(hoja)
    filas: list[list] = []

    for publicacion in publicaciones:

        link = str(publicacion.get("link", "")).strip()

        if not link or link in links_existentes:
            continue

        filas.append(
            [
                publicacion.get("fecha_captura", ""),
                publicacion.get("grupo", ""),
                publicacion.get("texto", ""),
                link,
                publicacion.get("respuesta_ia", ""),
                publicacion.get("categoria", ""),
                publicacion.get("confianza", ""),
                (
                    "Guardar"
                    if publicacion.get("es_reclamo")
                    else "Descartar"
                ),
                "",
                "",
                publicacion.get("tipo", "publicacion"),
            ]
        )

        links_existentes.add(link)

    if filas:
        hoja.append_rows(
            filas,
            value_input_option="USER_ENTERED",
        )

    return len(filas)
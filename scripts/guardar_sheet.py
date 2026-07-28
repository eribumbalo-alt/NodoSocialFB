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
]
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

def preparar_hoja(hoja) -> None:
    """Crea o corrige los encabezados."""

    primera_fila = hoja.row_values(1)

    if primera_fila != COLUMNAS:
        hoja.update(
            range_name="A1:L1",
            values=[COLUMNAS],
        )


def obtener_links_existentes(hoja) -> set[str]:
    """Lee la columna link para evitar duplicados."""

    # El link ahora está en la columna 4.
    valores = hoja.col_values(4)

    if valores and valores[0].strip().lower() == "link":
        valores = valores[1:]

    return {
        valor.strip()
        for valor in valores
        if valor.strip()
    }


def guardar_reclamos_sheet(
    reclamos: list[dict],
) -> int:
    """Guarda únicamente reclamos nuevos."""

    if not reclamos:
        return 0

    hoja = conectar_google_sheet()
    preparar_hoja(hoja)

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
    """Guarda todas las publicaciones analizadas."""

    if not publicaciones:
        return 0

    hoja = conectar_google_sheet("Dataset IA")

    primera_fila = hoja.row_values(1)

    if primera_fila != COLUMNAS_DATASET:
        hoja.update(
            range_name="A1:J1",
            values=[COLUMNAS_DATASET],
        )

    filas = []

    for publicacion in publicaciones:

        filas.append([
            publicacion.get("fecha_captura", ""),
            publicacion.get("grupo", ""),
            publicacion.get("texto", ""),
            publicacion.get("link", ""),
            publicacion.get("respuesta_ia", ""),
            publicacion.get("categoria", ""),
            publicacion.get("confianza", ""),
            "Guardar" if publicacion.get("es_reclamo") else "Descartar",
            "",
            "",
        ])

    hoja.append_rows(
        filas,
        value_input_option="USER_ENTERED",
    )

    return len(filas)
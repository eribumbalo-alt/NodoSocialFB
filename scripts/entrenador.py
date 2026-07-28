from __future__ import annotations

import json

from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"

ARCHIVO_DATASET = (
    KNOWLEDGE_DIR / "dataset_entrenamiento.jsonl"
)

ARCHIVO_METRICAS = (
    KNOWLEDGE_DIR / "metricas.json"
)

ARCHIVO_CREDENCIALES = (
    BASE_DIR / "config" / "credenciales_google.json"
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

NOMBRE_SPREADSHEET = "Nodo Social Reclamos"
NOMBRE_HOJA = "Dataset IA"


def conectar_sheet():
    """Conecta con la hoja Dataset IA."""

    credenciales = Credentials.from_service_account_file(
        str(ARCHIVO_CREDENCIALES),
        scopes=SCOPES,
    )

    cliente = gspread.authorize(credenciales)

    spreadsheet = cliente.open(NOMBRE_SPREADSHEET)

    return spreadsheet.worksheet(NOMBRE_HOJA)


def leer_dataset():
    """Lee todas las filas del Dataset IA."""

    hoja = conectar_sheet()

    registros = hoja.get_all_records()

    print(f"Publicaciones encontradas: {len(registros)}")

    return registros


def obtener_validados(registros):
    """Devuelve solo las publicaciones con validación humana."""

    validados = []

    for fila in registros:

        validacion = str(
            fila.get("validacion_humana", "")
        ).strip()

        if validacion:
            validados.append(fila)

    return validados

def generar_dataset_entrenamiento(validados):
    """Genera dataset_entrenamiento.jsonl"""

    cantidad = 0

    with open(
        ARCHIVO_DATASET,
        "w",
        encoding="utf-8",
    ) as archivo:

        for fila in validados:

            validacion = (
                fila.get(
                    "validacion_humana",
                    "",
                )
                .strip()
                .lower()
            )

            registro = {
                "texto": fila.get("texto", ""),
                "categoria": fila.get(
                    "categoria_ia",
                    "",
                ),
                "es_reclamo": False,
            }

            if validacion == "correcto":

                registro["es_reclamo"] = (
                    fila.get(
                        "respuesta_ia",
                        "",
                    ).lower()
                    == "reclamo"
                )

            elif validacion == "falso positivo":

                registro["es_reclamo"] = False

            elif validacion == "falso negativo":

                registro["es_reclamo"] = True

            else:
                continue

            archivo.write(
                json.dumps(
                    registro,
                    ensure_ascii=False,
                )
            )

            archivo.write("\n")

            cantidad += 1

    return cantidad

def generar_metricas(validados):

    metricas = {
        "publicaciones": len(validados),
        "correctos": 0,
        "falsos_positivos": 0,
        "falsos_negativos": 0,
        "categoria_incorrecta": 0,
        "dudosos": 0,
        "precision": 0,
    }

    for fila in validados:

        decision = (
            fila.get(
                "validacion_humana",
                "",
            )
            .strip()
            .lower()
        )

        if decision == "correcto":
            metricas["correctos"] += 1

        elif decision == "falso positivo":
            metricas["falsos_positivos"] += 1

        elif decision == "falso negativo":
            metricas["falsos_negativos"] += 1

        elif decision == "categoría incorrecta":
            metricas["categoria_incorrecta"] += 1

        elif decision == "dudoso":
            metricas["dudosos"] += 1

    if metricas["publicaciones"]:

        metricas["precision"] = round(
            metricas["correctos"]
            / metricas["publicaciones"]
            * 100,
            2,
        )

    with open(
        ARCHIVO_METRICAS,
        "w",
        encoding="utf-8",
    ) as archivo:

        json.dump(
            metricas,
            archivo,
            ensure_ascii=False,
            indent=4,
        )

    return metricas

def entrenar():

    print("=" * 40)
    print("ENTRENADOR NODO SOCIAL")
    print("=" * 40)

    print("\nConectando con Google Sheets...\n")

    registros = leer_dataset()

    validados = obtener_validados(
        registros
    )

    cantidad = generar_dataset_entrenamiento(
        validados
    )

    metricas = generar_metricas(
        validados
    )

    print(
        f"Publicaciones validadas: {len(validados)}"
    )

    print(
        f"Dataset generado: {cantidad} ejemplos"
    )

    print()

    print("RESUMEN")
    print("-" * 30)

    print(
        f"Correctos: {metricas['correctos']}"
    )

    print(
        f"Falsos positivos: {metricas['falsos_positivos']}"
    )

    print(
        f"Falsos negativos: {metricas['falsos_negativos']}"
    )

    print(
        f"Categorías incorrectas: {metricas['categoria_incorrecta']}"
    )

    print(
        f"Dudosos: {metricas['dudosos']}"
    )

    print(
        f"Precisión: {metricas['precision']}%"
    )

    print()

    print(
        f"Archivo dataset: {ARCHIVO_DATASET}"
    )

    print(
        f"Archivo métricas: {ARCHIVO_METRICAS}"
    )

if __name__ == "__main__":
    entrenar()
from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent.parent

KNOWLEDGE = BASE_DIR / "knowledge"


def cargar_json(nombre):

    archivo = KNOWLEDGE / nombre

    with open(
        archivo,
        encoding="utf-8",
    ) as f:

        return json.load(f)


def guardar_json(nombre, datos):

    archivo = KNOWLEDGE / nombre

    with open(
        archivo,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            datos,
            f,
            ensure_ascii=False,
            indent=4,
        )


def categorias():

    return cargar_json(
        "categorias.json"
    )


def palabras():

    return cargar_json(
        "palabras_clave.json"
    )


def ejemplos():

    return cargar_json(
        "ejemplos.json"
    )


def metricas():

    return cargar_json(
        "metricas.json"
    )
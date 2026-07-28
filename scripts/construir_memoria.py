from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

KNOWLEDGE_DIR = BASE_DIR / "knowledge"

ARCHIVO_DATASET = (
    KNOWLEDGE_DIR / "dataset_entrenamiento.jsonl"
)

ARCHIVO_MEMORIA = (
    KNOWLEDGE_DIR / "memoria_clasificador.json"
)

def leer_dataset():

    ejemplos = []

    with open(
        ARCHIVO_DATASET,
        encoding="utf-8",
    ) as archivo:

        for linea in archivo:

            linea = linea.strip()

            if not linea:
                continue

            ejemplos.append(
                json.loads(linea)
            )

    return ejemplos

def construir_memoria():

    ejemplos = leer_dataset()

    memoria = {
        "version": 1,
        "ultima_actualizacion": "",
        "ejemplos": ejemplos,
    }

    with open(
        ARCHIVO_MEMORIA,
        "w",
        encoding="utf-8",
    ) as archivo:

        json.dump(
            memoria,
            archivo,
            ensure_ascii=False,
            indent=4,
        )

    print(
        f"Ejemplos cargados: {len(ejemplos)}"
    )

if __name__ == "__main__":
    construir_memoria()
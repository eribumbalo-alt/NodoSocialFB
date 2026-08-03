"""Revisa la calidad de los ejemplos guardados en la memoria.

Uso:
    python scripts/revisar_memoria.py

No modifica nada. Solo muestra que hay adentro de
knowledge/memoria_clasificador.json para saber cuanto material
sirve y cuanto es basura de la interfaz de Facebook.
"""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ARCHIVO_MEMORIA = BASE_DIR / "knowledge" / "memoria_clasificador.json"

# Textos que aparecen en la interfaz de Facebook y no en una
# publicacion real. Si el texto capturado los contiene, es muy
# probable que el scraper haya agarrado basura del DOM.
RUIDO_INTERFAZ = [
    "Responder",
    "Compartir",
    "Me gusta",
    "Ver traduccion",
    "Ver traducción",
    "Ver mas",
    "Ver más",
    "Comentar",
    "Editado",
    "Todos los comentarios",
    "Comentarios mas relevantes",
    "Comentarios más relevantes",
]

LARGO_MINIMO = 60


def cargar() -> list[dict]:

    if not ARCHIVO_MEMORIA.exists():
        print(f"No existe el archivo: {ARCHIVO_MEMORIA}")
        return []

    with open(ARCHIVO_MEMORIA, encoding="utf-8") as archivo:
        memoria = json.load(archivo)

    return memoria.get("ejemplos", [])


def motivos_de_sospecha(texto: str) -> list[str]:
    """Devuelve las razones por las que un texto parece basura."""

    motivos = []

    for marca in RUIDO_INTERFAZ:
        if marca in texto:
            motivos.append(f"contiene '{marca}'")

    if len(texto.strip()) < LARGO_MINIMO:
        motivos.append(f"muy corto ({len(texto.strip())} caracteres)")

    if "·" in texto:
        motivos.append("contiene separador de metadatos")

    return motivos


def limpiar_para_mostrar(texto: str, largo: int = 110) -> str:

    plano = " ".join(texto.split())

    if len(plano) > largo:
        return plano[:largo] + "..."

    return plano


def main() -> None:

    ejemplos = cargar()

    if not ejemplos:
        print("No hay ejemplos para revisar.")
        return

    limpios = []
    sospechosos = []

    for indice, ejemplo in enumerate(ejemplos, start=1):

        texto = str(ejemplo.get("texto", ""))
        motivos = motivos_de_sospecha(texto)

        registro = (indice, ejemplo, motivos)

        if motivos:
            sospechosos.append(registro)
        else:
            limpios.append(registro)

    # ------------------------------------------------------
    # RESUMEN
    # ------------------------------------------------------

    total = len(ejemplos)

    print("=" * 70)
    print("CALIDAD DE LOS EJEMPLOS")
    print("=" * 70)
    print(f"Total de ejemplos      : {total}")
    print(
        f"Parecen publicaciones  : {len(limpios)} "
        f"({len(limpios) * 100 // total}%)"
    )
    print(
        f"Parecen basura de UI   : {len(sospechosos)} "
        f"({len(sospechosos) * 100 // total}%)"
    )
    print()

    # ------------------------------------------------------
    # BALANCE DE ETIQUETAS
    # ------------------------------------------------------

    reclamos = sum(
        1 for e in ejemplos
        if str(e.get("es_reclamo")).lower() == "true"
    )

    print("-" * 70)
    print("BALANCE DE ETIQUETAS")
    print("-" * 70)
    print(f"es_reclamo = true      : {reclamos}")
    print(f"es_reclamo = false     : {total - reclamos}")
    print()

    conteo: dict[str, int] = {}

    for ejemplo in ejemplos:
        categoria = str(ejemplo.get("categoria", "(sin categoria)"))
        conteo[categoria] = conteo.get(categoria, 0) + 1

    print("Por categoria:")

    for categoria, cantidad in sorted(
        conteo.items(),
        key=lambda par: par[1],
        reverse=True,
    ):
        print(f"   {cantidad:3}  {categoria}")

    print()

    # ------------------------------------------------------
    # DETALLE
    # ------------------------------------------------------

    print("-" * 70)
    print("SOSPECHOSOS")
    print("-" * 70)

    if not sospechosos:
        print("Ninguno.")

    for indice, ejemplo, motivos in sospechosos:
        print(f"\n[{indice}] {limpiar_para_mostrar(str(ejemplo.get('texto', '')))}")
        print(f"     etiqueta: {ejemplo.get('categoria')}")
        print(f"     motivo  : {', '.join(motivos)}")

    print()
    print("-" * 70)
    print("PARECEN PUBLICACIONES REALES")
    print("-" * 70)

    if not limpios:
        print("Ninguno. El dataset no tiene material utilizable.")

    for indice, ejemplo, _ in limpios:
        print(f"\n[{indice}] {limpiar_para_mostrar(str(ejemplo.get('texto', '')))}")
        print(
            f"     es_reclamo: {ejemplo.get('es_reclamo')}  |  "
            f"categoria: {ejemplo.get('categoria')}"
        )

    print()


if __name__ == "__main__":
    main()
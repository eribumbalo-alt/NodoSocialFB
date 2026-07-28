from pathlib import Path
import sys


BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.guardar_sheet import guardar_reclamos_sheet


reclamo_prueba = {
    "fecha_captura": "2026-07-14 12:00:00",
    "grupo": "Grupo de prueba",
    "puntaje": "5",
    "coincidencias": "basura, hace días",
    "texto": "Este es un reclamo de prueba.",
    "link": "https://www.facebook.com/post-prueba-nodo-social",
}

cantidad = guardar_reclamos_sheet([reclamo_prueba])

print(f"Filas agregadas: {cantidad}")
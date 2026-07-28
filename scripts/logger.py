from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent.parent

CARPETA_LOGS = BASE_DIR / "logs"

CARPETA_LOGS.mkdir(exist_ok=True)


nombre_log = datetime.now().strftime("%Y-%m-%d_%H-%M-%S.log")

ARCHIVO_LOG = CARPETA_LOGS / nombre_log


class Logger:

    def __init__(self):

        self.archivo = open(
            ARCHIVO_LOG,
            "a",
            encoding="utf-8"
        )

    def escribir(self, texto):

        hora = datetime.now().strftime("%H:%M:%S")

        linea = f"[{hora}] {texto}"

        print(linea)

        self.archivo.write(linea + "\n")

        self.archivo.flush()

    def separador(self):

        self.escribir("=" * 80)

    def cerrar(self):

        self.archivo.close()


logger = Logger()
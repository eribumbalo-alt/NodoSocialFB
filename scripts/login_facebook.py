from playwright.sync_api import sync_playwright

CARPETA_PERFIL = "perfil_facebook_nodo"

with sync_playwright() as p:
    contexto = p.chromium.launch_persistent_context(
        user_data_dir=CARPETA_PERFIL,
        headless=False,
        viewport={"width": 1366, "height": 768}
    )

    pagina = contexto.new_page()
    pagina.goto("https://www.facebook.com", wait_until="domcontentloaded")

    print("Iniciá sesión en Facebook en la ventana que se abrió.")
    print("Entrá a un grupo y verificá que ves publicaciones.")
    print("Cuando termines, volvé a esta terminal y presioná ENTER.")

    input("Presioná ENTER para cerrar...")

    contexto.close()
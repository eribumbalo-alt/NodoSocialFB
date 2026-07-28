from playwright.sync_api import sync_playwright

with sync_playwright() as p:

    navegador = p.chromium.launch(
        headless=False
    )

    contexto = navegador.new_context(
        storage_state="facebook_sesion.json"
    )

    pagina = contexto.new_page()

    pagina.goto(
        "https://www.facebook.com"
    )

    print("Facebook abierto con sesión guardada")

    pagina.wait_for_timeout(10000)

    navegador.close()

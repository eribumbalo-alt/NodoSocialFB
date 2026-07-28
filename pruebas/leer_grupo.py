from playwright.sync_api import sync_playwright
from urllib.parse import urljoin

URL_GRUPO = "https://www.facebook.com/groups/feed/"

PALABRAS_RECLAMO = [
    "reclamo", "urgente", "nadie responde", "abandono",
    "basura", "luminaria", "luz", "agua", "cloaca",
    "bache", "calle rota", "pérdida", "robo", "inseguridad",
    "poda", "árbol", "perros", "municipio", "delegación",
    "hace días", "hace semanas", "peligro", "no pasa",
    "no arreglan", "no vienen", "sin luz", "sin agua",
    "calle", "vecinos", "solución"
]

def parece_reclamo(texto):
    texto_lower = texto.lower()
    cantidad = sum(1 for palabra in PALABRAS_RECLAMO if palabra in texto_lower)

    frases_reclamo = [
        "alguien sabe",
        "hasta cuándo",
        "quién se hace cargo",
        "necesitamos solución",
        "por favor",
        "hace días",
        "hace semanas",
        "nadie responde"
    ]

    tiene_frase = any(frase in texto_lower for frase in frases_reclamo)

    return cantidad >= 2 or tiene_frase


def limpiar_link(link):
    if not link:
        return ""
    if link.startswith("/"):
        return urljoin("https://www.facebook.com", link)
    return link


with sync_playwright() as p:
    navegador = p.chromium.launch(headless=False)
    contexto = navegador.new_context(storage_state="facebook_sesion.json")
    pagina = contexto.new_page()

    print("Entrando al grupo...")
    pagina.goto(URL_GRUPO, wait_until="domcontentloaded")
    pagina.wait_for_timeout(12000)

    for _ in range(6):
        pagina.mouse.wheel(0, 2000)
        pagina.wait_for_timeout(3000)

    publicaciones = pagina.locator('div[role="article"]')
    cantidad = publicaciones.count()

    print(f"Publicaciones encontradas: {cantidad}")

    reclamos = []

    for i in range(cantidad):
        post = publicaciones.nth(i)

        try:
            texto = post.inner_text(timeout=5000).strip()
        except:
            texto = ""

        if not texto or len(texto) < 40:
            continue

        try:
            links = post.locator("a").evaluate_all("""
                els => els
                    .map(a => a.href)
                    .filter(h =>
                        h.includes('/posts/') ||
                        h.includes('/permalink/') ||
                        h.includes('story_fbid') ||
                        h.includes('/groups/')
                    )
            """)
        except:
            links = []

        link_post = limpiar_link(links[0]) if links else URL_GRUPO

        if parece_reclamo(texto):
            reclamos.append({
                "texto": texto,
                "link": link_post
            })

    print(f"\nReclamos detectados: {len(reclamos)}")

    for i, reclamo in enumerate(reclamos[:10], start=1):
        print(f"\n---------- RECLAMO {i} ----------")
        print(reclamo["texto"][:1000])
        print("\nLINK:")
        print(reclamo["link"])

    navegador.close()
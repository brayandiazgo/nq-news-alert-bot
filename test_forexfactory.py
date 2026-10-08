from playwright.sync_api import sync_playwright
from datetime import datetime

URL = "https://www.forexfactory.com/calendar"


# ============================================================
# EVENTOS QUE BLOQUEAN NQ
# ============================================================

def es_evento_bloqueo(nombre):
    nombre = nombre.lower()

    # CPI / IPC
    if "cpi" in nombre or "consumer price index" in nombre:
        return "CPI / IPC"

    # PPI / IPP
    if "ppi" in nombre or "producer price index" in nombre:
        return "PPI / IPP"

    # FOMC Minutes / Actas
    if "fomc meeting minutes" in nombre:
        return "FOMC MINUTES"

    return None


# ============================================================
# PMI
# ============================================================

def es_pmi(nombre):
    nombre = nombre.lower()

    if "pmi" in nombre:
        return True

    return False


# ============================================================
# CALENDARIO
# ============================================================

with sync_playwright() as p:

    browser = p.chromium.launch(headless=True)

    page = browser.new_page(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/155.0.0.0 Safari/537.36"
        )
    )

    print("Abriendo Forex Factory...")

    response = page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    print("HTTP:", response.status if response else "Sin respuesta")
    print("Título:", page.title())

    page.wait_for_timeout(5000)

    print("\nBuscando eventos relevantes para NQ...\n")

    # Buscar todas las filas del calendario
    filas = page.locator("tr.calendar__row")

    encontrados = 0

    for i in range(filas.count()):

        fila = filas.nth(i)

        texto = fila.inner_text().strip()

        if not texto:
            continue

        # Solo nos interesan eventos USD
        if "USD" not in texto:
            continue

        nombre = ""

        # Intentar obtener nombre del evento
        try:
            nombre = fila.locator(
                ".calendar__event-title"
            ).inner_text().strip()
        except:
            pass

        if not nombre:
            continue

        bloqueo = es_evento_bloqueo(nombre)

        if bloqueo:

            print("=" * 60)
            print("🔴 NQ — NO SE OPERA ESTA SESIÓN")
            print("Evento:", nombre)
            print("Motivo:", bloqueo)
            print("=" * 60)

            encontrados += 1

        elif es_pmi(nombre):

            print("=" * 60)
            print("🟡 NQ — ESPERAR PMI")
            print("Evento:", nombre)
            print("Regla: NO operar antes del PMI")
            print("Regla: OPERAR DESPUÉS DEL PMI")
            print("=" * 60)

            encontrados += 1

    print("\n" + "=" * 60)
    print("TOTAL EVENTOS RELEVANTES:", encontrados)
    print("=" * 60)

    browser.close()

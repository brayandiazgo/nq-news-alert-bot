from playwright.sync_api import sync_playwright
from urllib.parse import urljoin

BASE_URL = "https://www.forexfactory.com/calendar"

SEMANAS = [
    ("4–10 OCTUBRE 2026", "oct4.2026"),
    ("11–17 OCTUBRE 2026", "oct11.2026"),
]


def clasificar_evento(nombre, texto):
    n = nombre.lower()
    t = texto.lower()

    # CPI / IPC
    if "cpi" in n or "consumer price index" in n:
        return "🔴", "NO SE OPERA ESTA SESIÓN", "CPI / IPC"

    # PPI / IPP
    if "ppi" in n or "producer price index" in n:
        return "🔴", "NO SE OPERA ESTA SESIÓN", "PPI / IPP"

    # FOMC Minutes
    if "fomc meeting minutes" in n or "fomc minutes" in n:
        return "🔴", "NO SE OPERA ESTA SESIÓN", "FOMC MINUTES"

    # PMI
    if "pmi" in n:
        return "🟡", "ESPERAR PMI → OPERAR DESPUÉS", "PMI"

    # Festivos / cierres
    if "bank holiday" in n or "holiday" in n:
        return "🏦", "REVISAR CIERRE DE NQ", "FESTIVO"

    return None


with sync_playwright() as p:

    browser = p.chromium.launch(headless=True)

    page = browser.new_page(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/155.0.0.0 Safari/537.36"
        )
    )

    total = 0

    for nombre_semana, semana in SEMANAS:

        url = f"{BASE_URL}?week={semana}"

        print("\n")
        print("=" * 70)
        print(f"📅 {nombre_semana}")
        print("=" * 70)

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(4000)

        filas = page.locator("tr.calendar__row")

        encontrados_semana = 0

        for i in range(filas.count()):

            fila = filas.nth(i)

            try:
                texto = fila.inner_text().strip()
            except:
                continue

            if not texto:
                continue

            # Solo USD
            if "USD" not in texto:
                continue

            try:
                evento = fila.locator(
                    ".calendar__event-title"
                ).inner_text().strip()
            except:
                continue

            if not evento:
                continue

            resultado = clasificar_evento(evento, texto)

            if not resultado:
                continue

            icono, regla, tipo = resultado

            # Hora
            try:
                hora = fila.locator(
                    ".calendar__time"
                ).inner_text().strip()
            except:
                hora = "Hora no disponible"

            # Intentamos obtener fecha de la fila
            try:
                fecha = fila.locator(
                    ".calendar__date"
                ).inner_text().strip()
            except:
                fecha = ""

            print()
            print("-" * 70)
            print(f"{icono} {tipo}")
            print(f"Evento: {evento}")
            print(f"Fecha: {fecha if fecha else 'Ver calendario'}")
            print(f"Hora: {hora}")
            print(f"Regla NQ: {regla}")
            print("-" * 70)

            encontrados_semana += 1
            total += 1

        print()
        print(
            f"Eventos relevantes encontrados: {encontrados_semana}"
        )

    print("\n")
    print("=" * 70)
    print(f"TOTAL GENERAL: {total}")
    print("=" * 70)

    browser.close()

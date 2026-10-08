from playwright.sync_api import sync_playwright

BASE_URL = "https://www.forexfactory.com/calendar"

SEMANAS = [
    ("4–10 OCTUBRE 2026", "oct4.2026", "oct10.2026"),
    ("11–17 OCTUBRE 2026", "oct11.2026", "oct17.2026"),
]


def clasificar_evento(nombre):
    n = nombre.lower()

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

    # Festivos USD
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

    for nombre_semana, desde, hasta in SEMANAS:

        url = f"{BASE_URL}?range={desde}-{hasta}"

        print("\n")
        print("=" * 70)
        print(f"📅 {nombre_semana}")
        print("=" * 70)

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(5000)

        filas = page.locator("tr.calendar__row")

        encontrados_semana = 0
        fecha_actual = ""

        for i in range(filas.count()):

            fila = filas.nth(i)

            try:
                texto = fila.inner_text().strip()
            except:
                continue

            if not texto:
                continue

            # --------------------------------------------------
            # DETECTAR FECHA
            # --------------------------------------------------

            try:
                fecha_elemento = fila.locator(".calendar__date")

                if fecha_elemento.count() > 0:
                    nueva_fecha = fecha_elemento.first.inner_text().strip()

                    if nueva_fecha:
                        fecha_actual = nueva_fecha

            except:
                pass

            # --------------------------------------------------
            # SOLO USD
            # --------------------------------------------------

            if "USD" not in texto:
                continue

            # --------------------------------------------------
            # OBTENER NOMBRE DEL EVENTO
            # --------------------------------------------------

            evento = ""

            try:
                titulo = fila.locator(".calendar__event-title")

                if titulo.count() > 0:
                    evento = titulo.first.inner_text().strip()
            except:
                pass

            # Si por alguna razón el selector no funciona,
            # buscamos directamente en el texto de la fila.
            if not evento:

                posibles = [
                    "FOMC Meeting Minutes",
                    "Final Services PMI",
                    "ISM Services PMI",
                    "CPI",
                    "Consumer Price Index",
                    "PPI",
                    "Producer Price Index",
                    "Bank Holiday",
                ]

                for posible in posibles:
                    if posible.lower() in texto.lower():
                        evento = posible
                        break

            if not evento:
                continue

            # --------------------------------------------------
            # CLASIFICAR
            # --------------------------------------------------

            resultado = clasificar_evento(evento)

            if not resultado:
                continue

            icono, regla, tipo = resultado

            # --------------------------------------------------
            # HORA
            # --------------------------------------------------

            try:
                hora_elemento = fila.locator(".calendar__time")

                if hora_elemento.count() > 0:
                    hora = hora_elemento.first.inner_text().strip()
                else:
                    hora = "Hora no disponible"

            except:
                hora = "Hora no disponible"

            # --------------------------------------------------
            # MOSTRAR
            # --------------------------------------------------

            print()
            print("-" * 70)
            print(f"{icono} {tipo}")
            print(f"Evento: {evento}")
            print(f"Fecha: {fecha_actual if fecha_actual else 'Ver calendario'}")
            print(f"Hora: {hora}")
            print(f"Regla NQ: {regla}")
            print("-" * 70)

            encontrados_semana += 1
            total += 1

        print()
        print(f"Eventos relevantes encontrados: {encontrados_semana}")

    print("\n")
    print("=" * 70)
    print(f"TOTAL GENERAL: {total}")
    print("=" * 70)

    browser.close()

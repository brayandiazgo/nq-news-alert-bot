from playwright.sync_api import sync_playwright
from datetime import datetime


BASE_URL = "https://www.forexfactory.com/calendar"

SEMANAS = [
    ("4–10 OCTUBRE 2026", "oct4.2026"),
    ("11–17 OCTUBRE 2026", "oct11.2026"),
]


def clasificar_evento(evento):
    n = evento.lower()

    # CPI / IPC
    if "cpi" in n or "consumer price index" in n:
        return "🔴", "CPI / IPC", "NO SE OPERA ESTA SESIÓN"

    # PPI / IPP
    if "ppi" in n or "producer price index" in n:
        return "🔴", "PPI / IPP", "NO SE OPERA ESTA SESIÓN"

    # FOMC Minutes
    if "fomc meeting minutes" in n:
        return "🔴", "FOMC MINUTES", "NO SE OPERA ESTA SESIÓN"

    if "fomc minutes" in n:
        return "🔴", "FOMC MINUTES", "NO SE OPERA ESTA SESIÓN"

    # PMI
    if "pmi" in n:
        return "🟡", "PMI", "ESPERAR PMI → OPERAR DESPUÉS"

    # Festivos
    if "bank holiday" in n or "holiday" in n:
        return "🏦", "FESTIVO", "REVISAR CIERRE DE NQ"

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

    for nombre_semana, week in SEMANAS:

        print()
        print("=" * 70)
        print(f"📅 {nombre_semana}")
        print("=" * 70)

        url = f"{BASE_URL}?week={week}"

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        # Esperar específicamente la tabla del calendario
        try:
            tbody = page.wait_for_selector(
                "#content section.content.calendar table tbody",
                timeout=30000
            )
        except:
            print("❌ No se encontró la tabla del calendario")
            continue

        # Esperar renderizado
        page.wait_for_timeout(3000)

        filas = tbody.query_selector_all("tr.calendar__row")

        fecha_actual = ""

        encontrados_semana = 0

        for fila in filas:

            # --------------------------------------------------
            # FECHA
            # --------------------------------------------------

            date_el = fila.query_selector(
                "td.calendar__date span"
            )

            if date_el:
                nueva_fecha = date_el.inner_text().strip()

                if nueva_fecha:
                    fecha_actual = nueva_fecha

            # --------------------------------------------------
            # MONEDA
            # --------------------------------------------------

            currency_el = fila.query_selector(
                "td.calendar__currency span"
            )

            if not currency_el:
                continue

            moneda = currency_el.inner_text().strip()

            if moneda != "USD":
                continue

            # --------------------------------------------------
            # EVENTO
            # --------------------------------------------------

            event_el = fila.query_selector(
                "span.calendar__event-title"
            )

            if not event_el:
                continue

            evento = event_el.inner_text().strip()

            if not evento:
                continue

            # --------------------------------------------------
            # CLASIFICACIÓN
            # --------------------------------------------------

            resultado = clasificar_evento(evento)

            if not resultado:
                continue

            icono, tipo, regla = resultado

            # --------------------------------------------------
            # HORA
            # --------------------------------------------------

            time_el = fila.query_selector(
                "td.calendar__time span"
            )

            if time_el:
                hora = time_el.inner_text().strip()
            else:
                hora = "Hora no disponible"

            # --------------------------------------------------
            # IMPACTO
            # --------------------------------------------------

            impact = "desconocido"

            impact_el = fila.query_selector(
                "td.calendar__impact span"
            )

            if impact_el:
                clases = impact_el.get_attribute("class") or ""

                if "ff-impact-red" in clases:
                    impact = "ALTO"
                elif "ff-impact-ora" in clases:
                    impact = "MEDIO"
                elif "ff-impact-yel" in clases:
                    impact = "BAJO"

            # --------------------------------------------------
            # RESULTADO
            # --------------------------------------------------

            print()
            print("-" * 70)
            print(f"{icono} {tipo}")
            print(f"Evento: {evento}")
            print(f"Fecha: {fecha_actual}")
            print(f"Hora: {hora}")
            print(f"Moneda: {moneda}")
            print(f"Impacto: {impact}")
            print(f"Regla NQ: {regla}")
            print("-" * 70)

            encontrados_semana += 1
            total += 1

        print()
        print(
            f"Eventos relevantes encontrados: {encontrados_semana}"
        )

    print()
    print("=" * 70)
    print(f"TOTAL GENERAL: {total}")
    print("=" * 70)

    browser.close()

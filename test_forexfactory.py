from playwright.sync_api import sync_playwright


BASE_URL = "https://www.forexfactory.com/calendar"


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

    browser = p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ]
    )

    page = browser.new_page(
        viewport={"width": 1920, "height": 1080},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    )

    # ----------------------------------------------------------
    # CARGAMOS OCTUBRE COMPLETO
    # ----------------------------------------------------------

    url = f"{BASE_URL}?month=october"

    print(f"Abriendo: {url}")

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(5000)

    # ----------------------------------------------------------
    # TABLA REAL DE FOREX FACTORY
    # ----------------------------------------------------------

    try:
        page.wait_for_selector(
            "table.calendar__table",
            timeout=30000
        )
    except:
        print("❌ No se encontró .calendar__table")

        print("\nTítulo:")
        print(page.title())

        print("\nURL:")
        print(page.url)

        browser.close()
        raise SystemExit(1)

    print("✅ Tabla Forex Factory encontrada")

    # ----------------------------------------------------------
    # SCROLL PARA ASEGURAR QUE SE CARGUE TODO
    # ----------------------------------------------------------

    ultima_altura = 0

    for _ in range(30):

        altura = page.evaluate(
            "document.body.scrollHeight"
        )

        if altura == ultima_altura:
            break

        ultima_altura = altura

        page.evaluate(
            "window.scrollTo(0, document.body.scrollHeight)"
        )

        page.wait_for_timeout(1000)

    # ----------------------------------------------------------
    # OBTENER TODAS LAS FILAS
    # ----------------------------------------------------------

    filas = page.locator(
        "table.calendar__table tr"
    )

    print(f"Filas encontradas: {filas.count()}")

    eventos = []

    fecha_actual = None

    for i in range(filas.count()):

        fila = filas.nth(i)

        # ------------------------------------------------------
        # FECHA
        # ------------------------------------------------------

        fecha_el = fila.locator(
            "td.calendar__cell.calendar__date"
        )

        if fecha_el.count() > 0:

            texto_fecha = fecha_el.first.inner_text().strip()

            if texto_fecha:
                fecha_actual = texto_fecha

        # ------------------------------------------------------
        # MONEDA
        # ------------------------------------------------------

        moneda_el = fila.locator(
            "td.calendar__cell.calendar__currency"
        )

        if moneda_el.count() == 0:
            continue

        moneda = moneda_el.first.inner_text().strip()

        if moneda != "USD":
            continue

        # ------------------------------------------------------
        # EVENTO
        # ------------------------------------------------------

        evento_el = fila.locator(
            "td.calendar__cell.calendar__event.event"
        )

        if evento_el.count() == 0:
            continue

        evento = evento_el.first.inner_text().strip()

        if not evento:
            continue

        # ------------------------------------------------------
        # CLASIFICAR
        # ------------------------------------------------------

        resultado = clasificar_evento(evento)

        if not resultado:
            continue

        icono, tipo, regla = resultado

        # ------------------------------------------------------
        # HORA
        # ------------------------------------------------------

        hora_el = fila.locator(
            "td.calendar__cell.calendar__time"
        )

        if hora_el.count() > 0:
            hora = hora_el.first.inner_text().strip()
        else:
            hora = "Hora no disponible"

        # ------------------------------------------------------
        # IMPACTO
        # ------------------------------------------------------

        impacto = "desconocido"

        impacto_el = fila.locator(
            "td.calendar__cell.calendar__impact"
        )

        if impacto_el.count() > 0:

            iconos = impacto_el.locator("span")

            for j in range(iconos.count()):

                clase = (
                    iconos.nth(j)
                    .get_attribute("class")
                    or ""
                )

                if "impact-red" in clase:
                    impacto = "ALTO"

                elif "impact-ora" in clase:
                    impacto = "MEDIO"

                elif "impact-yel" in clase:
                    impacto = "BAJO"

        # ------------------------------------------------------
        # GUARDAR
        # ------------------------------------------------------

        eventos.append({
            "fecha": fecha_actual or "Desconocida",
            "hora": hora,
            "evento": evento,
            "tipo": tipo,
            "icono": icono,
            "regla": regla,
            "impacto": impacto,
        })

    # ----------------------------------------------------------
    # MOSTRAR SOLO NUESTRAS DOS SEMANAS
    # ----------------------------------------------------------

    total = 0

    semanas = {
        "4–10 OCTUBRE 2026": [
            "Oct 5",
            "Oct 6",
            "Oct 7",
            "Oct 8",
            "Oct 9",
        ],
        "11–17 OCTUBRE 2026": [
            "Oct 12",
            "Oct 13",
            "Oct 14",
            "Oct 15",
            "Oct 16",
        ],
    }

    for nombre_semana, fechas in semanas.items():

        print()
        print("=" * 70)
        print(f"📅 {nombre_semana}")
        print("=" * 70)

        encontrados = 0

        for evento in eventos:

            fecha = evento["fecha"]

            if fecha not in fechas:
                continue

            print()
            print("-" * 70)
            print(
                f'{evento["icono"]} {evento["tipo"]}'
            )
            print(
                f'Evento: {evento["evento"]}'
            )
            print(
                f'Fecha: {evento["fecha"]}'
            )
            print(
                f'Hora: {evento["hora"]}'
            )
            print(
                f'Impacto: {evento["impacto"]}'
            )
            print(
                f'Regla NQ: {evento["regla"]}'
            )
            print("-" * 70)

            encontrados += 1
            total += 1

        print()
        print(
            f"Eventos relevantes encontrados: {encontrados}"
        )

    print()
    print("=" * 70)
    print(f"TOTAL GENERAL: {total}")
    print("=" * 70)

    browser.close()

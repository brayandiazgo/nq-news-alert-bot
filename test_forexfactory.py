from playwright.sync_api import sync_playwright

URL = "https://www.forexfactory.com/calendar"

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
    print("URL final:", page.url)

    page.wait_for_timeout(5000)

    texto = page.locator("body").inner_text()

    print("\n--- PRIMEROS 3000 CARACTERES ---\n")
    print(texto[:3000])

    browser.close()

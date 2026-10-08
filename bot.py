import os
import requests


def enviar_telegram(mensaje):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    respuesta = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": mensaje
        },
        timeout=30
    )

    respuesta.raise_for_status()
    return respuesta.json()


if __name__ == "__main__":
    enviar_telegram(
        "🧪 PRUEBA — Bot NQ\n\n"
        "GitHub Actions → Python → Telegram ✅"
    )

    print("Mensaje enviado correctamente.")

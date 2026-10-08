# Bot NQ: noticias de Forex Factory a Telegram

Avisa solo de lo que cambia tu operación en **NQ**:

| Evento (USD) | Aviso |
|---|---|
| CPI, PPI, FOMC Minutes | 🔴 NO SE OPERA ESTA SESIÓN |
| PMI (Final, ISM, Flash…) | 🟡 ESPERAR PMI → OPERAR DESPUÉS, y 🟢 "ya puedes operar" cuando sale el último |
| Festivo USD | 🏦 solo dice "NO SE OPERA" si la fecha está en `cme_closures.json`; si no, avisa que falta confirmar con CME |

## Cómo funciona

- `scrape.yml` corre una vez al día (5:30 am Bogotá, lun-vie): lee el feed JSON semanal de Forex Factory (`nfs.faireconomy.media`, no pasa por Cloudflare), guarda `state/events.json` y manda el resumen del día. Si el feed falla, usa Playwright como respaldo (Cloudflare suele bloquearlo desde GitHub).
- **Resumen semanal** (esta semana y la próxima): llega solo los domingos a las 6:00 pm Bogotá, o cuando quieras desde Actions → "NQ - leer calendario" → Run workflow → marcar *weekly*. La próxima semana aparece solo cuando Forex Factory ya la publicó; si no, dice "Sin datos todavía".
- `check.yml` corre cada 15 min (5:00 am a 6:45 pm Bogotá): lee `state/events.json` (sin navegador) y manda el aviso previo (`LEAD_MIN`, por defecto 30 min) y el "ya salió". `state/sent.json` evita duplicados.
- Si Forex Factory bloquea la lectura, el bot te avisa por Telegram en vez de quedarse callado.

## Puesta en marcha

1. Sube estos archivos a tu repo (incluida la carpeta `.github/workflows`).
2. Secrets del repo: `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID` (ya los tienes).
3. Settings → Actions → General → Workflow permissions → **Read and write permissions**.
4. Actions → "NQ - leer calendario" → Run workflow. Revisa el log: imprime la fuente usada ("feed"), las filas leídas y los eventos relevantes.
5. Comprueba las horas: FOMC Minutes debe salir 2:00 pm ET = 1:00 pm Bogotá; el mensaje muestra las dos zonas para que lo veas.

## Ajustes

- `LEAD_MIN` (env en `check.yml`): minutos de aviso previo; `0` lo desactiva.
- `cme_closures.json`: fechas `YYYY-MM-DD` de cierre/cierre temprano de NQ, tomadas de cmegroup.com/trading-hours.
- Reglas: lista `RULES` al inicio de `nq_bot.py`.

## Pruebas sin red

```
python test_nq_bot.py
```

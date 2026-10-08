#!/usr/bin/env python3
"""Bot NQ: avisos de noticias de Forex Factory por Telegram.

Uso:
  python nq_bot.py scrape                 lee el calendario (feed JSON de Forex Factory; si falla,
                                          Playwright), guarda state/events.json y manda el resumen
  python nq_bot.py scrape --weekly        igual, pero manda el resumen de esta semana y la próxima
  python nq_bot.py check                  lee state/events.json y manda avisos previos / "ya salió"
                                          (sin navegador, es rápido)
  python nq_bot.py parse-file f.html YYYY-MM   prueba el parser con un HTML guardado

Variables de entorno:
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID   (GitHub Secrets)
  FF_TZ      zona en la que se lee Forex Factory (por defecto America/Bogota)
  LEAD_MIN   minutos de anticipación del aviso previo (por defecto 30; 0 = sin aviso previo)
  DRY_RUN=1  imprime en vez de enviar a Telegram
"""
from __future__ import annotations

import html as htmllib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
EVENTS_FILE = STATE_DIR / "events.json"
SENT_FILE = STATE_DIR / "sent.json"
CME_FILE = ROOT / "cme_closures.json"

FF_TZ = ZoneInfo(os.getenv("FF_TZ", "America/Bogota"))
LOCAL_TZ = ZoneInfo("America/Bogota")
ET = ZoneInfo("America/New_York")
LEAD_MIN = int(os.getenv("LEAD_MIN", "30"))
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ───────────────────────── Reglas NQ ─────────────────────────
# (tipo, regex sobre el título del evento USD, acción)
RULES = [
    ("CPI", r"\bCPI\b", "NO_TRADE"),
    ("PPI", r"\bPPI\b", "NO_TRADE"),
    ("FOMC_MINUTES", r"FOMC\s+(Meeting\s+)?Minutes", "NO_TRADE"),
    ("PMI", r"\bPMI\b", "WAIT"),
]
HOLIDAY_RX = re.compile(
    r"holiday|thanksgiving|christmas|new year|independence|labor day|memorial|"
    r"martin luther|presidents|juneteenth|columbus|veterans|good friday",
    re.I,
)
ICON = {"CPI": "🔴", "PPI": "🔴", "FOMC_MINUTES": "🔴", "PMI": "🟡", "HOLIDAY": "🏦"}
ACTION_TXT = {
    "NO_TRADE": "NO SE OPERA ESTA SESIÓN",
    "WAIT": "ESPERAR PMI → OPERAR DESPUÉS",
}

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_RE = re.compile(
    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\s*"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*(\d{1,2})", re.I)
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)", re.I)


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


# ───────────────────────── Parser ─────────────────────────
def parse_calendar(page_html: str, ref_year: int, ref_month: int, tz=None) -> list[dict]:
    """Convierte el HTML del calendario de Forex Factory en una lista de eventos."""
    from bs4 import BeautifulSoup

    tz = tz or FF_TZ
    soup = BeautifulSoup(page_html, "html.parser")
    out: list[dict] = []
    cur_date: date | None = None
    cur_time = ""

    for tr in soup.select("tr.calendar__row"):
        date_td = tr.select_one("td.calendar__date")
        if date_td:
            m = DATE_RE.search(clean(date_td.get_text(" ")))
            if m:
                mon, day = MONTHS[m.group(1).lower()], int(m.group(2))
                year = ref_year
                if ref_month == 12 and mon == 1:
                    year += 1
                elif ref_month == 1 and mon == 12:
                    year -= 1
                try:
                    cur_date = date(year, mon, day)
                    cur_time = ""
                except ValueError:
                    continue

        title_el = tr.select_one(".calendar__event-title")
        if not title_el or cur_date is None:
            continue
        title = clean(title_el.get_text())

        cur_el = tr.select_one("td.calendar__currency")
        currency = clean(cur_el.get_text()) if cur_el else ""

        impact = ""
        imp_td = tr.select_one("td.calendar__impact")
        if imp_td:
            classes = " ".join(c for el in imp_td.select("[class]") for c in el.get("class", []))
            mm = re.search(r"impact-(red|ora|yel|gra)", classes)
            impact = mm.group(1) if mm else ""

        time_td = tr.select_one("td.calendar__time")
        ttxt = clean(time_td.get_text(" ")) if time_td else ""
        if ttxt:  # una celda vacía significa "misma hora que la fila anterior"
            cur_time = ttxt
        dt = None
        tm = TIME_RE.search(cur_time)
        if tm:
            h = int(tm.group(1)) % 12 + (12 if tm.group(3).lower() == "pm" else 0)
            dt = datetime(cur_date.year, cur_date.month, cur_date.day, h, int(tm.group(2)), tzinfo=tz)

        out.append({"date": cur_date, "dt": dt, "currency": currency,
                    "impact": impact, "title": title})
    return out


def classify(ev: dict) -> str | None:
    """Devuelve el tipo de regla NQ que aplica al evento, o None."""
    if ev["currency"] != "USD":
        return None
    for kind, rx, _ in RULES:
        if re.search(rx, ev["title"], re.I):
            return kind
    if ev["impact"] == "gra" and ev["dt"] is None and HOLIDAY_RX.search(ev["title"]):
        return "HOLIDAY"
    return None


def relevant(events: list[dict]) -> list[dict]:
    """Filtra eventos USD que afectan a NQ y agrupa los que salen a la misma hora."""
    groups: dict[tuple, dict] = {}
    for ev in events:
        kind = classify(ev)
        if not kind:
            continue
        when = ev["dt"].isoformat() if ev["dt"] else ev["date"].isoformat()
        g = groups.setdefault((when, kind), {
            "id": f"{when}|{kind}",
            "kind": kind,
            "action": "HOLIDAY" if kind == "HOLIDAY" else dict((k, a) for k, _, a in RULES)[kind],
            "date": ev["date"].isoformat(),
            "dt": ev["dt"].isoformat() if ev["dt"] else None,
            "titles": [],
        })
        if ev["title"] not in g["titles"]:
            g["titles"].append(ev["title"])
    return sorted(groups.values(), key=lambda g: (g["dt"] or g["date"], g["kind"]))


# ───────────────────────── Formato de mensajes ─────────────────────────
def hora(dt: datetime) -> str:
    def f(x: datetime) -> str:
        return x.strftime("%I:%M %p").lstrip("0").lower()
    return f"{f(dt.astimezone(LOCAL_TZ))} Bogotá ({f(dt.astimezone(ET))} ET)"


def day_label(d: date) -> str:
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}"


def load_closures() -> dict:
    try:
        return json.loads(CME_FILE.read_text())
    except Exception:
        return {"closed": [], "early_close": []}


def holiday_action(d: str) -> str:
    c = load_closures()
    if d in c.get("closed", []):
        return "🏦 NO SE OPERA: CME confirma cierre de NQ"
    if d in c.get("early_close", []):
        return "🏦 CME cierra temprano: revisa el horario antes de operar"
    return ("⚠️ Festivo en Forex Factory, pero NO está confirmado el cierre de NQ. "
            "Revisa cmegroup.com/trading-hours antes de decidir")


def event_block(g: dict) -> str:
    titles = htmllib.escape(", ".join(g["titles"]))
    when = f" — {hora(datetime.fromisoformat(g['dt']))}" if g["dt"] else ""
    if g["action"] == "HOLIDAY":
        action = holiday_action(g["date"])
    else:
        action = f"{ICON[g['kind']]} {ACTION_TXT[g['action']]}"
    return f"{ICON[g['kind']]} <b>{titles}</b>{when}\n   {action}"


def next_weekday(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def build_digest(rel: list[dict], today: date) -> str:
    def section(d: date) -> list[str]:
        return [event_block(g) for g in rel if g["date"] == d.isoformat()]

    lines = [f"📅 <b>NQ — {day_label(today)}</b>"]
    todays = section(today)
    lines += todays if todays else ["✅ Hoy sin noticias que afecten NQ."]
    tmr = next_weekday(today)
    tm = section(tmr)
    if tm:
        lines += ["", f"<i>Siguiente día hábil ({day_label(tmr)}):</i>"] + tm
    return "\n".join(lines)


def week_monday(today: date) -> date:
    """Lunes de la semana que importa: el domingo ya cuenta la semana que empieza mañana."""
    return today + timedelta(days=1) if today.weekday() == 6 else today - timedelta(days=today.weekday())


def short_line(g: dict) -> str:
    d = date.fromisoformat(g["date"])
    titles = htmllib.escape(", ".join(g["titles"]))
    when = ""
    if g["dt"]:
        b = datetime.fromisoformat(g["dt"]).astimezone(LOCAL_TZ)
        when = " · " + b.strftime("%I:%M %p").lstrip("0").lower()
    if g["action"] == "HOLIDAY":
        closed = g["date"] in load_closures().get("closed", [])
        act = "NO SE OPERA (CME cerrado)" if closed else "festivo USD, falta confirmar CME"
    else:
        act = {"NO_TRADE": "NO SE OPERA", "WAIT": "ESPERAR → OPERAR DESPUÉS"}[g["action"]]
    return f"{ICON[g['kind']]} {DIAS[d.weekday()][:3]} {d.day} {MESES[d.month - 1]}{when} · <b>{titles}</b> → {act}"


def build_weekly(rel: list[dict], today: date, data_until: date | None) -> str:
    """Resumen de esta semana y la próxima (lunes a viernes, hora de Bogotá)."""
    mon = week_monday(today)

    def section(start: date, label: str) -> list[str]:
        end = start + timedelta(days=4)
        head = f"<b>{label}</b> ({start.day} {MESES[start.month - 1]} – {end.day} {MESES[end.month - 1]})"
        if data_until is not None and data_until < start:
            return [head, "Sin datos todavía: Forex Factory aún no publica esa semana."]
        evs = [g for g in rel if start.isoformat() <= g["date"] <= end.isoformat()]
        return [head] + ([short_line(g) for g in evs] if evs else ["✅ Sin noticias que afecten NQ."])

    return "\n".join(["🗓 <b>NQ — resumen semanal</b>", ""]
                     + section(mon, "Esta semana") + [""] + section(mon + timedelta(days=7), "Próxima semana"))


# ───────────────────────── Estado y Telegram ─────────────────────────
def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def telegram(text: str) -> None:
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if os.getenv("DRY_RUN") or not token or not chat:
        print("──[Telegram, no enviado]──\n" + text + "\n─────────────")
        return
    body = urllib.parse.urlencode({
        "chat_id": chat, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def mark_sent(sent: dict, key: str, now: datetime) -> None:
    sent[key] = now.isoformat()
    cutoff = now - timedelta(days=14)
    for k in [k for k, v in sent.items() if datetime.fromisoformat(v) < cutoff]:
        del sent[k]


# ───────────────────────── Modo check (avisos) ─────────────────────────
def run_check(events: list[dict], sent: dict, now: datetime, send=telegram) -> int:
    """Manda avisos previos y de 'ya salió'. Devuelve cuántos mensajes envió."""
    n = 0
    timed = [g for g in events if g["dt"]]
    for g in timed:
        t = datetime.fromisoformat(g["dt"])
        titles = htmllib.escape(", ".join(g["titles"]))
        until = t - now

        # 1) Aviso previo
        pre = f"{g['id']}|pre"
        if LEAD_MIN > 0 and timedelta(0) < until <= timedelta(minutes=LEAD_MIN) and pre not in sent:
            mins = max(1, int(until.total_seconds() // 60))
            send(f"⏰ <b>En {mins} min</b>: {titles} ({hora(t)})\n"
                 f"{ICON[g['kind']]} {ACTION_TXT[g['action']]}")
            mark_sent(sent, pre, now)
            n += 1

        # 2) Ya salió (hasta 60 min después, por si GitHub se atrasa)
        at = f"{g['id']}|at"
        if timedelta(0) <= -until <= timedelta(minutes=60) and at not in sent:
            if g["action"] == "NO_TRADE":
                msg = f"🔴 Ya salió: <b>{titles}</b>. Hoy NO se opera esta sesión."
            else:
                pending = [x for x in timed if x["action"] == "WAIT" and x["date"] == g["date"]
                           and datetime.fromisoformat(x["dt"]) > t]
                if pending:
                    nxt = pending[0]
                    msg = (f"🟡 Salió <b>{titles}</b>. Aún falta: "
                           f"{htmllib.escape(', '.join(nxt['titles']))} "
                           f"({hora(datetime.fromisoformat(nxt['dt']))}). Sigue esperando.")
                else:
                    msg = f"🟢 Ya salió <b>{titles}</b>: ya puedes operar."
            send(msg)
            mark_sent(sent, at, now)
            n += 1
    return n


def cmd_check() -> None:
    data = load_json(EVENTS_FILE, None)
    if not data:
        print("No hay state/events.json todavía: corre primero el workflow de scrape.")
        return
    now = datetime.now(LOCAL_TZ)
    sent = load_json(SENT_FILE, {})
    n = run_check(data["events"], sent, now)
    save_json(SENT_FILE, sent)
    print(f"check {now:%Y-%m-%d %H:%M} Bogotá: {n} mensaje(s) enviados")


# ───────────────────────── Fuente 1: feed JSON (sin Cloudflare) ─────────────────────────
FEEDS = [  # (url, obligatorio)
    ("https://nfs.faireconomy.media/ff_calendar_thisweek.json", True),
    ("https://nfs.faireconomy.media/ff_calendar_nextweek.json", False),
]
IMPACT_MAP = {"high": "red", "medium": "ora", "low": "yel", "holiday": "gra"}


def http_json(url: str, tries: int = 3):
    last: Exception | None = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except Exception as exc:  # red, JSON roto, etc.
            last = exc
        if i < tries - 1:
            time.sleep(20 * (i + 1))
    raise RuntimeError(f"{url.rsplit('/', 1)[-1]}: {last}")


def parse_feed(items: list[dict]) -> list[dict]:
    """Convierte el feed JSON al mismo formato de evento que usa el parser HTML."""
    out = []
    for it in items:
        try:
            dt = datetime.fromisoformat(it["date"])
        except (KeyError, ValueError):
            continue
        if dt.tzinfo is None:  # el feed viene en hora de Nueva York
            dt = dt.replace(tzinfo=ET)
        impact = IMPACT_MAP.get(str(it.get("impact", "")).lower(), "")
        if impact == "gra":  # festivo: solo cuenta la fecha, no la hora
            out.append({"date": dt.date(), "dt": None, "currency": it.get("country", ""),
                        "impact": impact, "title": clean(it.get("title", ""))})
        else:
            out.append({"date": dt.astimezone(LOCAL_TZ).date(), "dt": dt,
                        "currency": it.get("country", ""), "impact": impact,
                        "title": clean(it.get("title", ""))})
    return out


def fetch_from_feed() -> list[dict]:
    events: list[dict] = []
    for url, required in FEEDS:
        try:
            events += parse_feed(http_json(url))
        except Exception as exc:
            if required:
                raise
            print(f"(opcional) {exc}")
    return events


# ───────────────────────── Fuente 2 (respaldo): navegador ─────────────────────────
def fetch_pages(targets: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"],
                   check=True)
    pages = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=UA, locale="en-US", timezone_id=FF_TZ.key,
                                  viewport={"width": 1366, "height": 900})
        ctx.add_cookies([{"name": "fftimezone", "value": FF_TZ.key,
                          "domain": ".forexfactory.com", "path": "/"}])
        page = ctx.new_page()
        for label, year, month in targets:
            url = f"https://www.forexfactory.com/calendar?month={label}"
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:  # sin recargar: recargar reinicia el desafío de Cloudflare
                page.wait_for_selector("tr.calendar__row", timeout=60000)
            except PWTimeout:
                raise RuntimeError(
                    f"Forex Factory no mostró el calendario ({label}); título: {page.title()!r}")
            for _ in range(4):  # por si carga filas al hacer scroll
                page.mouse.wheel(0, 6000)
                page.wait_for_timeout(500)
            pages.append((page.content(), year, month))
        browser.close()
    return pages


def cmd_scrape(weekly: bool = False) -> None:
    now = datetime.now(LOCAL_TZ)
    today = now.date()
    targets = [("this", today.year, today.month)]
    later = today + timedelta(days=14)
    if (later.year, later.month) != (today.year, today.month):
        targets.append(("next", later.year, later.month))

    sent = load_json(SENT_FILE, {})
    events: list[dict] = []
    source = "feed"
    errors: list[str] = []
    try:
        events = fetch_from_feed()
    except Exception as exc:
        errors.append(f"feed: {exc}")
        print(f"El feed falló ({exc}); intento con el navegador…")
    if not events:
        source = "navegador"
        try:
            for page_html, y, m in fetch_pages(targets):
                events += parse_calendar(page_html, y, m)
        except Exception as exc:
            errors.append(f"navegador: {exc}")
    if not events:  # avisar en vez de quedarse ciego en silencio
        key = f"error|{today}"
        if key not in sent:
            telegram("⚠️ <b>Bot NQ</b>: hoy no pude leer el calendario "
                     f"({htmllib.escape(' | '.join(errors))[:300]}). Revisa las noticias a mano.")
            mark_sent(sent, key, now)
            save_json(SENT_FILE, sent)
        raise SystemExit("scrape falló: " + " | ".join(errors))

    rel = relevant(events)
    usd = [e for e in events if e["currency"] == "USD"]
    data_until = max(e["date"] for e in events)
    save_json(EVENTS_FILE, {"generated_at": now.isoformat(), "source": source,
                            "data_until": data_until.isoformat(),
                            "rows_total": len(events), "rows_usd": len(usd), "events": rel})
    print(f"Fuente: {source} | filas: {len(events)} | USD: {len(usd)} | relevantes para NQ: {len(rel)}")
    for g in rel:
        print(" ", g["dt"] or g["date"], g["kind"], g["titles"])

    if weekly:  # se pide a mano o el domingo: siempre se envía
        telegram(build_weekly(rel, today, data_until))
    else:
        key = f"digest|{today}"
        if key not in sent:
            telegram(build_digest(rel, today))
            mark_sent(sent, key, now)
    save_json(SENT_FILE, sent)


def cmd_parse_file(path: str, ym: str) -> None:
    y, m = (int(x) for x in ym.split("-"))
    events = parse_calendar(Path(path).read_text(), y, m)
    rel = relevant(events)
    print(f"{len(events)} filas, {len(rel)} relevantes")
    for g in rel:
        print(g["dt"] or g["date"], g["kind"], g["titles"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "scrape":
        cmd_scrape(weekly="--weekly" in sys.argv[2:])
    elif cmd == "check":
        cmd_check()
    elif cmd == "parse-file" and len(sys.argv) == 4:
        cmd_parse_file(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(2)

"""Pruebas sin red: parser, reglas NQ, avisos y anti-duplicados."""
import os
from datetime import datetime, timedelta

os.environ["DRY_RUN"] = "1"
import nq_bot as b  # noqa: E402


def row(date_txt, time_txt, cur, impact, title):
    d = (f'<td class="calendar__cell calendar__date"><span class="date">'
         f'<span>{date_txt[:3]}</span> <span>{date_txt[4:]}</span></span></td>') if date_txt else \
        '<td class="calendar__cell calendar__date"></td>'
    t = f'<td class="calendar__cell calendar__time"><span>{time_txt}</span></td>'
    return (f'<tr class="calendar__row">{d}{t}'
            f'<td class="calendar__cell calendar__currency"><span>{cur}</span></td>'
            f'<td class="calendar__cell calendar__impact"><span class="icon icon--ff-impact-{impact}"></span></td>'
            f'<td class="calendar__cell calendar__event"><span class="calendar__event-title">{title}</span></td></tr>')


HTML = "<table><tbody>" + "".join([
    '<tr class="calendar__row calendar__row--day-breaker"><td>Mon</td></tr>',
    row("Mon Oct 5", "8:45am", "USD", "yel", "Final Services PMI"),
    row("", "9:00am", "USD", "ora", "ISM Services PMI"),
    row("", "9:00am", "EUR", "red", "ECB President Speaks"),
    row("Wed Oct 7", "1:00pm", "USD", "red", "FOMC Meeting Minutes"),
    row("", "", "USD", "ora", "Crude Oil Inventories"),   # hora en blanco = misma hora de arriba
    row("Thu Oct 8", "7:30am", "USD", "red", "CPI m/m"),
    row("", "7:30am", "USD", "red", "Core CPI m/m"),
    row("", "7:30am", "USD", "ora", "Unemployment Claims"),  # no relevante
    row("Mon Oct 12", "All Day", "USD", "gra", "Bank Holiday"),
    row("", "All Day", "JPY", "gra", "Bank Holiday"),         # otra moneda: se ignora
    row("Tue Oct 13", "7:30am", "USD", "red", "PPI m/m"),
]) + "</tbody></table>"

events = b.parse_calendar(HTML, 2026, 10)
rel = b.relevant(events)
by = {(g["kind"], g["dt"] or g["date"]): g for g in rel}

# --- parser y reglas ---
assert len(events) == 11, len(events)
kinds = [g["kind"] for g in rel]
assert kinds == ["PMI", "PMI", "FOMC_MINUTES", "CPI", "HOLIDAY", "PPI"], kinds
assert rel[0]["dt"] == "2026-10-05T08:45:00-05:00"
fomc = by[("FOMC_MINUTES", "2026-10-07T13:00:00-05:00")]
assert fomc["titles"] == ["FOMC Meeting Minutes"]
cpi = [g for g in rel if g["kind"] == "CPI"]
assert len(cpi) == 1 and cpi[0]["titles"] == ["CPI m/m", "Core CPI m/m"]
# la fila con hora en blanco el miércoles hereda 1:00 pm
blank = [e for e in events if e["title"] == "Crude Oil Inventories"][0]
assert blank["dt"].hour == 13 and blank["date"].day == 7
assert b.classify(blank) is None                          # no es una noticia de las reglas
assert all(g["titles"] != ["ECB President Speaks"] for g in rel)  # otra moneda: fuera
print("parser y reglas OK")

# --- mensajes: 1:00 pm Bogotá = 2:00 pm ET ---
assert "1:00 pm Bogotá (2:00 pm ET)" in b.event_block(fomc)
d = b.build_digest(rel, datetime(2026, 10, 7).date())
assert "NO SE OPERA ESTA SESIÓN" in d and "FOMC Meeting Minutes" in d
d_mon = b.build_digest(rel, datetime(2026, 10, 5).date())
assert "ESPERAR PMI" in d_mon and "FOMC" not in d_mon
d_hol = b.build_digest(rel, datetime(2026, 10, 12).date())
assert "NO está confirmado el cierre" in d_hol
print("mensajes OK")

# --- avisos y anti-duplicados ---
sent_msgs = []
sent = {}
tz = b.LOCAL_TZ


def run(now):
    return b.run_check(rel, sent, now, send=lambda m: sent_msgs.append(m))


t_pmi1 = datetime(2026, 10, 5, 8, 45, tzinfo=tz)
assert run(t_pmi1 - timedelta(minutes=45)) == 0           # muy temprano
assert run(t_pmi1 - timedelta(minutes=20)) == 1           # aviso previo
assert run(t_pmi1 - timedelta(minutes=10)) == 1           # entra a ventana el ISM de las 9:00
assert "ISM Services PMI" in sent_msgs[-1]
assert run(t_pmi1 - timedelta(minutes=9)) == 0            # sin duplicar
n = run(t_pmi1 + timedelta(minutes=2))                    # salió el primero; falta el ISM
assert n >= 1 and "Aún falta" in sent_msgs[-1], sent_msgs[-1]
assert run(t_pmi1 + timedelta(minutes=6)) == 0            # sin duplicar
run(datetime(2026, 10, 5, 9, 3, tzinfo=tz))               # salió el último PMI
assert "ya puedes operar" in sent_msgs[-1], sent_msgs[-1]
t_fomc = datetime(2026, 10, 7, 13, 0, tzinfo=tz)
run(t_fomc + timedelta(minutes=1))
assert "Hoy NO se opera" in sent_msgs[-1]
assert run(t_fomc + timedelta(minutes=3)) == 0
assert run(t_fomc + timedelta(hours=3)) == 0              # muy tarde: no manda nada viejo
print("avisos y anti-duplicados OK")
# --- feed JSON (fuente principal) ---
FEED = [
    {"title": "Final Services PMI", "country": "USD", "date": "2026-10-05T09:45:00-04:00", "impact": "Low"},
    {"title": "ISM Services PMI", "country": "USD", "date": "2026-10-05T10:00:00-04:00", "impact": "Medium"},
    {"title": "Final Services PMI", "country": "EUR", "date": "2026-10-05T04:00:00-04:00", "impact": "Low"},
    {"title": "PPI m/m", "country": "EUR", "date": "2026-10-05T05:00:00-04:00", "impact": "Low"},
    {"title": "FOMC Member Bowman Speaks", "country": "USD", "date": "2026-10-06T10:45:00-04:00", "impact": "Low"},
    {"title": "FOMC Meeting Minutes", "country": "USD", "date": "2026-10-07T14:00:00-04:00", "impact": "High"},
    {"title": "CPI m/m", "country": "USD", "date": "2026-10-14T08:30:00-04:00", "impact": "High"},
    {"title": "Core CPI m/m", "country": "USD", "date": "2026-10-14T08:30:00-04:00", "impact": "High"},
    {"title": "Bank Holiday", "country": "USD", "date": "2026-10-12T00:00:00-04:00", "impact": "Holiday"},
    {"title": "Bank Holiday", "country": "CNY", "date": "2026-10-05T19:01:00-04:00", "impact": "Holiday"},
    {"title": "Basura sin fecha", "country": "USD", "date": "no-es-fecha", "impact": "High"},
]
fe = b.parse_feed(FEED)
assert len(fe) == 10                                       # la fila rota se descarta
frel = b.relevant(fe)
fk = [(g["kind"], g["dt"] or g["date"]) for g in frel]
assert fk == [
    ("PMI", "2026-10-05T09:45:00-04:00"), ("PMI", "2026-10-05T10:00:00-04:00"),
    ("FOMC_MINUTES", "2026-10-07T14:00:00-04:00"), ("HOLIDAY", "2026-10-12"),
    ("CPI", "2026-10-14T08:30:00-04:00")], fk            # EUR y los "FOMC Member…" quedan fuera
fomc_f = [g for g in frel if g["kind"] == "FOMC_MINUTES"][0]
assert "1:00 pm Bogotá (2:00 pm ET)" in b.event_block(fomc_f)
cpi_f = [g for g in frel if g["kind"] == "CPI"][0]
assert cpi_f["titles"] == ["CPI m/m", "Core CPI m/m"] and cpi_f["date"] == "2026-10-14"
print("feed OK")

# --- resumen semanal ---
from datetime import date  # noqa: E402

thu = date(2026, 10, 8)
assert b.week_monday(thu) == date(2026, 10, 5)
assert b.week_monday(date(2026, 10, 11)) == date(2026, 10, 12)   # domingo -> semana que empieza mañana
w = b.build_weekly(frel, thu, date(2026, 10, 16))
this_part, next_part = w.split("<b>Próxima semana</b>")
assert "Esta semana" in this_part and "5 oct – 9 oct" in this_part
assert "lun 5 oct · 8:45 am · <b>Final Services PMI</b>" in this_part
assert "mié 7 oct · 1:00 pm · <b>FOMC Meeting Minutes</b> → NO SE OPERA" in this_part
assert "12 oct – 16 oct" in next_part
assert "lun 12 oct · <b>Bank Holiday</b> → festivo USD, falta confirmar CME" in next_part
assert "mié 14 oct · 7:30 am · <b>CPI m/m, Core CPI m/m</b> → NO SE OPERA" in next_part
w2 = b.build_weekly(frel, thu, date(2026, 10, 9))                 # el feed solo llega hasta el viernes
assert "Sin datos todavía" in w2.split("<b>Próxima semana</b>")[1]
w3 = b.build_weekly([], thu, date(2026, 10, 16))
assert w3.count("Sin noticias que afecten NQ") == 2
print("semanal OK")
print(w)

print("TODO OK")

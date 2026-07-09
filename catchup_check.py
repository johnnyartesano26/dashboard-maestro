#!/usr/bin/env python3
"""Decide si corresponde ejecutar el catch-up de festivos.

Regla: se ejecuta el catch-up SÓLO si:
  1) hoy es día hábil (no fin de semana, no festivo en Colombia), y
  2) el archivo objetivo NO se ha actualizado (commit) desde el lunes de esta semana.

Así cubre el caso de un lunes festivo (o PC apagada): el primer día hábil
siguiente hace la actualización. En una semana normal (la PC actualizó el lunes)
no hace nada, evitando duplicados.

Uso: python3 catchup_check.py <archivo_objetivo>
Escribe 'run=1' o 'run=0' en $GITHUB_OUTPUT.
"""
import sys, os, json, subprocess, urllib.request
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    COT = ZoneInfo("America/Bogota")
except Exception:
    COT = timezone(timedelta(hours=-5))

# Respaldo por si la API de festivos no responde (festivos Colombia 2026)
FALLBACK = {
    2026: {
        "2026-01-01", "2026-01-12", "2026-03-23", "2026-04-02", "2026-04-03",
        "2026-05-01", "2026-05-18", "2026-06-08", "2026-06-15", "2026-06-29",
        "2026-07-20", "2026-08-07", "2026-08-17", "2026-10-12", "2026-11-02",
        "2026-11-16", "2026-12-08", "2026-12-25",
    }
}

target = sys.argv[1] if len(sys.argv) > 1 else None


def emit(run, reason):
    print(f"run={run}  ({reason})")
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a") as f:
            f.write(f"run={run}\n")
    sys.exit(0)


now = datetime.now(COT)
today = now.date()
wd = today.weekday()  # lunes=0 ... domingo=6

if wd >= 5:
    emit(0, "fin de semana")

# Festivos de Colombia (API con respaldo local)
holidays = set()
try:
    url = f"https://date.nager.at/api/v3/PublicHolidays/{today.year}/CO"
    with urllib.request.urlopen(url, timeout=15) as r:
        holidays = {h["date"] for h in json.load(r)}
except Exception as e:
    print(f"AVISO: no se pudo consultar la API de festivos ({e}); uso respaldo local.")
    holidays = FALLBACK.get(today.year, set())

if today.isoformat() in holidays:
    emit(0, "hoy es festivo (no es día hábil)")

# Lunes de esta semana a las 00:00 COT
monday = datetime.combine(today - timedelta(days=wd), datetime.min.time(), COT)

# Última fecha de commit del archivo objetivo
last = None
try:
    iso = subprocess.check_output(
        ["git", "log", "-1", "--format=%cI", "--", target]
    ).decode().strip()
    if iso:
        last = datetime.fromisoformat(iso)
except Exception as e:
    print(f"AVISO: no se pudo leer git log de {target} ({e}).")

if last is not None and last >= monday:
    emit(0, f"ya se actualizó esta semana ({last.isoformat()})")

emit(1, "corresponde catch-up: no se actualizó desde el lunes")

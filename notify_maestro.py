#!/usr/bin/env python3
"""Envía informe del Dashboard Maestro por Telegram leyendo catalogo.json.
Usa TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID del entorno."""
import json, os, sys, urllib.request

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT = os.environ.get("TELEGRAM_CHAT_ID")
CAMBIOS = os.environ.get("HUBO_CAMBIOS", "1") == "1"

if not TOKEN or not CHAT:
    print("Sin credenciales de Telegram; no se envía aviso.")
    sys.exit(0)

with open(os.path.join(os.path.dirname(__file__), "catalogo.json"), encoding="utf-8") as f:
    cat = json.load(f)
p = cat["periodos"][-1]
vb = p.get("ventas_bar", {}) or {}

msg = "🏛️ <b>Dashboard Maestro — Catch-up festivo</b>\n\n"
if CAMBIOS:
    msg += f"✅ <b>Actualizado:</b> {p.get('mes')}\n"
else:
    msg += f"📅 <b>{p.get('mes')}</b> · sin cambios (ya estaba al día)\n"
if vb:
    msg += f"🍺 Ventas Bar: ${vb.get('total_ventas', 0):,} · {vb.get('dias_con_dato', '?')} días\n"
    if vb.get("promedio_diario"):
        msg += f"📈 Promedio/día: ${vb['promedio_diario']:,}\n"
    if vb.get("crecimiento") is not None:
        msg += f"📊 Crecimiento: {vb['crecimiento']}%\n"
    if vb.get("meta_mes"):
        msg += f"🎯 Meta mes: ${vb['meta_mes']:,}\n"
msg += '\n🔗 <a href="https://johnnyartesano26.github.io/dashboard-maestro/">Dashboard Maestro</a>'

body = json.dumps({"chat_id": CHAT, "text": msg, "parse_mode": "HTML"}).encode()
req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                            data=body, headers={"Content-Type": "application/json"})
resp = json.load(urllib.request.urlopen(req, timeout=15))
print("Telegram enviado:", resp.get("ok"), resp.get("description", ""))

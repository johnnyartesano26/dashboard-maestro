#!/bin/bash
# update_all_dashboards.sh — Sincroniza todos los dashboards desde Google Sheets
# Ejecutado por cron diario a las 2 PM.
set -e

export MADREMONTE_KEY="Anderle01!"
LOG=/tmp/madremonte_all_dashboards.log

# Obtener token de GitHub para push HTTPS (SSH:22 bloqueado en esta red)
GH_TOKEN=$(python3 -c "
import sys; sys.path.insert(0,'/mnt/c/DeepAgente')
import os; os.environ['MADREMONTE_KEY']='Anderle01!'
from env_loader import load_credentials; load_credentials()
print(os.getenv('GITHUB_TOKEN',''))
")

git_push() {
    # $1 = repo dir, $2 = repo path (owner/repo)
    local dir="$1" repo="$2"
    git -C "$dir" remote set-url origin "https://x-access-token:${GH_TOKEN}@github.com/${repo}.git"
    git -C "$dir" push origin main >> $LOG 2>&1 && echo "  ✅ Push OK" >> $LOG || echo "  ⚠️ Push falló" >> $LOG
    git -C "$dir" remote set-url origin "https://github.com/${repo}.git"
}

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === Sincronización diaria de dashboards ===" >> $LOG

# ── 1. Bar Dashboard (madremonte-dashboard) ──
D1=/mnt/c/Users/USUARIO/madremonte-dashboard
echo "[$(date)] Paso 1: Bar Dashboard ($D1)" >> $LOG
cd "$D1"
if python3 update_bar_dashboard.py >> $LOG 2>&1; then
    if ! git diff --quiet bar.html; then
        git add bar.html update_bar_dashboard.py update_and_push.sh
        git commit -m "Auto: $(date '+%Y-%m-%d %H:%M')" >> $LOG 2>&1
        git_push "$D1" "johnnyartesano26/madremonte-dashboard"
    else
        echo "  Sin cambios" >> $LOG
    fi
else
    echo "  ❌ Error en update_bar_dashboard.py" >> $LOG
fi

# ── 2. Dashboard Maestro ──
D2=/mnt/c/Users/USUARIO/dashboard-maestro
echo "[$(date)] Paso 2: Dashboard Maestro ($D2)" >> $LOG
cd "$D2"
if python3 update_catalogo_maestro.py >> $LOG 2>&1; then
    if ! git diff --quiet catalogo.json; then
        git add catalogo.json update_catalogo_maestro.py update_all_dashboards.sh
        git commit -m "Auto: $(date '+%Y-%m-%d %H:%M')" >> $LOG 2>&1
        git_push "$D2" "johnnyartesano26/dashboard-maestro"
    else
        echo "  Sin cambios" >> $LOG
    fi
else
    echo "  ❌ Error en update_catalogo_maestro.py" >> $LOG
fi

# ── 3. Informe Telegram ──
echo "[$(date)] Paso 3: Enviando informe..." >> $LOG
python3 -c "
import sys; sys.path.insert(0,'/mnt/c/DeepAgente')
import os; os.environ['MADREMONTE_KEY']='Anderle01!'
from env_loader import load_credentials; load_credentials()
token = os.getenv('TELEGRAM_BOT_TOKEN','')
cid = os.getenv('TELEGRAM_CHAT_ID','8068061566')

import json, re, requests

msg = '📊 <b>Dashboard Maestro — Resumen Diario</b>\n\n'

# Leer bar dashboard
with open('$D1/bar.html') as f:
    c = f.read()
m = re.search(r'window\.BAR_DATA = (\{.*?\});', c, re.DOTALL)
bar = json.loads(m.group(1).rstrip(';'))
ultima = bar['hojas'][-1]
t = bar['totales']

msg += f'🍺 <b>Bar:</b> {ultima[\"nombre\"]}\n'
msg += f'   Días: {len(ultima[\"datos\"])} · Total mes: \${ultima[\"totalesMes\"][\"cierreAlegra\"]:,}\n'
msg += f'   Acumulado: \${t[\"cierreAlegra\"]:,} (Alegra) | \${t[\"cierreFormato\"]:,} (Formato)\n\n'

# Leer catalogo maestro
with open('$D2/catalogo.json') as f:
    cat = json.load(f)
ultimo_periodo = cat['periodos'][-1]
vb = ultimo_periodo.get('ventas_bar', {})

msg += f'🏛️ <b>Maestro:</b> {ultimo_periodo[\"mes\"]}\n'
msg += f'   Ventas Bar: \${vb.get(\"total_ventas\",0):,} · {vb.get(\"dias_con_dato\",\"?\")} días\n'
if vb.get('crecimiento'):
    msg += f'   Crecimiento: {vb[\"crecimiento\"]}%\n'
msg += f'   Meta: \${vb.get(\"meta_mes\",\"—\")}\n\n'
msg += f'🔗 <a href=\"https://johnnyartesano26.github.io/dashboard-maestro/\">Dashboard Maestro</a>\n'
msg += f'🔗 <a href=\"https://johnnyartesano26.github.io/madremonte-dashboard/bar.html\">Bar Dashboard</a>'

requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
    json={'chat_id': cid, 'text': msg, 'parse_mode': 'HTML'}, timeout=10)
print('TG informe enviado')
" >> $LOG 2>&1

echo "[$(date)] ✅ Sincronización completada" >> $LOG

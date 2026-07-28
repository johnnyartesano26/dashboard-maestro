#!/bin/bash
# update_inventario_neto.sh — Ejecuta nucleo_de_inventario.py y pushea inventario_neto.json
# Ejecutado por cron: 11:00 AM y 5:30 PM
set -e

# Cargar credenciales desde .env (fuera del repo, nunca en GitHub)
ENV_FILE="$HOME/.config/madremonte/.env"
if [ -f "$ENV_FILE" ]; then
    set -a; source "$ENV_FILE"; set +a
else
    echo "[$(date)] ⚠️  $ENV_FILE no encontrado. Algunas funciones fallarán." >&2
fi

LOG=/tmp/inventario_neto.log
NUCLEO_DIR="/mnt/c/Users/USUARIO/Documents/Madre Monte/MadreMonte_Contexto/inventario/registro_de_inventario"
REPO_DIR="/mnt/c/Users/USUARIO/dashboard-maestro"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === Actualizando inventario neto ===" >> $LOG

# Esperar a que haya internet (máx 2 min)
for i in $(seq 1 24); do
    if curl -s --connect-timeout 3 https://google.com > /dev/null 2>&1; then
        echo "[$(date)] Conexión a internet OK" >> $LOG
        break
    fi
    echo "[$(date)] Esperando internet... ($i/24)" >> $LOG
    sleep 5
done

# Asegurar que el remote use SSH (HTTPS token puede expirar)
git -C "$REPO_DIR" remote set-url origin git@github.com:johnnyartesano26/dashboard-maestro.git 2>>$LOG

# Backup del JSON anterior
cp "$REPO_DIR/data/inventario_neto.json" /tmp/inventario_neto_backup.json 2>/dev/null || true

# Ejecutar núcleo de inventario
echo "[$(date)] Ejecutando nucleo_de_inventario.py..." >> $LOG
cd "$NUCLEO_DIR"
python3 nucleo_de_inventario.py >> $LOG 2>&1
RET=$?

if [ $RET -ne 0 ]; then
    echo "[$(date)] ❌ nucleo_de_inventario.py falló con código $RET" >> $LOG
    exit $RET
fi

# Verificar si el JSON se generó
JSON_FILE="$REPO_DIR/data/inventario_neto.json"
if [ ! -f "$JSON_FILE" ]; then
    echo "[$(date)] ❌ inventario_neto.json no fue generado" >> $LOG
    exit 1
fi

echo "[$(date)] ✅ nucleo_de_inventario.py completado" >> $LOG

# Verificar si hay cambios respecto al backup
if ! diff -q "$JSON_FILE" /tmp/inventario_neto_backup.json > /dev/null 2>&1; then
    echo "[$(date)] Cambios detectados en inventario_neto.json. Pusheando..." >> $LOG
    
    cd "$REPO_DIR"
    git add data/inventario_neto.json update_inventario_neto.sh
    
    # Commit con resumen
    RESUMEN=$(python3 -c "
import json
with open('$JSON_FILE') as f:
    d = json.load(f)
t = d.get('totales', {})
barr = sum(b.get('litros', 0) for b in d.get('barriles', []))
bot = sum(b.get('cantidad', 0) for b in d.get('botellas', []))
print(f'Inv: {t.get(\"litros_fermentando\",0)}L ferm | {barr}L barril | {bot} bot | \${t.get(\"ventas_cop\",0):,} COP')
" 2>/dev/null)
    
    git commit -m "Auto-inv: $(date '+%Y-%m-%d %H:%M') — $RESUMEN" >> $LOG 2>&1
    
    # Push con SSH
    git push origin main >> $LOG 2>&1 && echo "[$(date)] ✅ Push OK" >> $LOG || echo "[$(date)] ⚠️ Push falló" >> $LOG

    # Telegram
    python3 -c "
import os, json, requests

token = os.getenv('TELEGRAM_BOT_TOKEN','')
cid = os.getenv('TELEGRAM_CHAT_ID','')
if token:
    import json, requests
    with open('$JSON_FILE') as f:
        d = json.load(f)
    t = d.get('totales',{})
    b_l = sum(b.get('litros',0) for b in d.get('barriles',[]))
    b_u = sum(b.get('cantidad',0) for b in d.get('botellas',[]))
    msg = f'🧬 <b>Inventario Neto Actualizado</b>\n\n'
    msg += f'📅 Lectura: {d.get(\"fecha_lectura\",\"?\")}\n'
    msg += f'🍺 Fermentadores: <b>{t.get(\"litros_fermentando\",0)} L</b>\n'
    msg += f'🛢️ Barriles: <b>{b_l} L</b>\n'
    msg += f'🍾 Botellas: <b>{b_u} uds</b>\n'
    msg += f'💰 Ventas COP: \${t.get(\"ventas_cop\",0):,}\n\n'
    msg += f'🔗 <a href=\"https://johnnyartesano26.github.io/dashboard-maestro/\">Dashboard Maestro</a>\n'
    msg += f'🔗 <a href=\"https://johnnyartesano26.github.io/madremonte-dashboard/\">Dashboard Planta</a>'
    requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
        json={'chat_id': cid, 'text': msg, 'parse_mode': 'HTML'}, timeout=10)
    print('TG enviado')
" >> $LOG 2>&1

else
    echo "[$(date)] Sin cambios en inventario_neto.json" >> $LOG
fi

echo "[$(date)] ✅ Finalizado" >> $LOG

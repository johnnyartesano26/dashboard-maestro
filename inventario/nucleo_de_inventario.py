#!/usr/bin/env python3
"""
nucleo_de_inventario_v2.py — Núcleo de Inventario con modo offline.
Puede leer desde Google Sheet + Alegra (online) o desde archivo local (offline).

Uso:
  python nucleo_de_inventario_v2.py           → modo online (Google Sheet + Alegra)
  python nucleo_de_inventario_v2.py --offline → modo offline (lee datos locales)
  python nucleo_de_inventario_v2.py --plantilla → genera plantilla para llenar manualmente
"""

import requests, json, os, sys
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ===================== CARGAR CREDENCIALES (desde .env) =====================
def _cargar_dotenv():
    """Carga variables de entorno desde ~/.config/madremonte/.env (sin depender de python-dotenv)."""
    paths = [
        os.path.expanduser("~/.config/madremonte/.env"),
        os.path.join(os.path.dirname(__file__), ".env"),
    ]
    for env_path in paths:
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, val = line.split('=', 1)
                    key, val = key.strip(), val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
            return True
    return False

_cargar_dotenv()

# ===================== CONFIGURACIÓN =====================
API_KEY = os.getenv("GOOGLE_API_KEY", "")
SHEET_ID_INVENTARIO = "1UHqPRV1stpnM5VHer9-8Z0H_UW0omiSoape7cIwzCGA"
ALEGRA_EMAIL = os.getenv("ALEGRA_EMAIL", "")
ALEGRA_TOKEN = os.getenv("ALEGRA_TOKEN", "")
ALEGRA_URL = "https://api.alegra.com/api/v1/"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_EXCEL = os.path.join(BASE_DIR, "nucleo_de_inventario.xlsx")
PLANTILLA_JSON = os.path.join(BASE_DIR, "plantilla_input_local.json")
ULTIMO_INVENTARIO_JSON = os.path.join(BASE_DIR, "ultimo_inventario_local.json")
HISTORIAL_JSON = os.path.join(BASE_DIR, "historial_inventario.json")

# Parámetros
BARRIL_L = 58.55
BOTELLA_L = 0.330
FONDO_BOTELLAS = 24
UMBRAL_ALARMA_BAJO = 120

ESTILOS = ['GOLDEN ALE', 'IRISH RED ALE', 'APA', 'IPA', 'STOUT', 'GERMAN PILS', 'HIDROMIEL', 'RED IPA', 'SCOTTISH']
CODIGOS_LITRO = {'GOLDEN ALE':'PTL01','IRISH RED ALE':'PTL02','APA':'PTL03','IPA':'PTL04','STOUT':'PTL05'}
CODIGOS_BOTELLA = {'GOLDEN ALE':'PTB01','IRISH RED ALE':'PTB02','APA':'PTB03','IPA':'PTB04','STOUT':'PTB05'}
PRECIOS_BOTELLA = {'PTB01':8500,'PTB02':8500,'PTB03':8500,'PTB04':9500,'PTB05':8500}
PRECIOS_LITRO = {'PTL01':18000,'PTL02':18000,'PTL03':18000,'PTL04':19000,'PTL05':18000}
CAPACIDADES = {'F1':400,'F2':1200,'F3':400,'F4':700,'F5':800,'F6':1000,'F7':500}

# Mapeo IDs Alegra → estilo + tipo
ID_ALEGRA_ESTILO = {
    '64':'GOLDEN ALE','65':'IRISH RED ALE','66':'APA','67':'IPA','68':'STOUT',
    '69':'GOLDEN ALE','70':'IRISH RED ALE','71':'APA','72':'IPA','73':'STOUT',
}
ID_ALEGRA_ES_BOTELLA = {'64','65','66','67','68'}
ID_ALEGRA_ES_LITRO = {'69','70','71','72','73'}
NOMBRES_FERM = ['F1 Frankie','F2 Igor','F3 Principito','F4 Gargantua','F5 Pantragruel','F6 Potter','F7 HighLander']

# Estilos
H_FILL = PatternFill(start_color='2F5496', end_color='2F5496', fill_type='solid')
H_FONT = Font(bold=True, color='FFFFFF', size=11)
T_FONT = Font(bold=True, size=14, color='2F5496')
INPUT_FILL = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
GREEN = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
YELLOW = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')
RED = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')
BORDER = Border(left=Side(style='thin'),right=Side(style='thin'),top=Side(style='thin'),bottom=Side(style='thin'))
WRAP = Alignment(wrap_text=True, vertical='top')
CENTER = Alignment(horizontal='center', vertical='center')

# ===================== VERIFICAR CONEXIÓN =====================
def hay_internet():
    try:
        requests.get('https://google.com', timeout=3)
        return True
    except:
        return False

# ===================== LECTURA ONLINE =====================
def _es_vacio(v):
    """True si la celda está vacía (None o string en blanco)."""
    return v is None or str(v).strip() == ''

def _to_float(v):
    """Convierte a float tolerando coma decimal (ej. '222,9' → 222.9) y separadores."""
    if _es_vacio(v):
        return None
    s = str(v).strip().replace(' ', '')
    if ',' in s and '.' in s:
        # '1.234,56' → asumir punto = miles, coma = decimal
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None

def _normalizar_fecha(raw):
    """Normaliza la marca temporal del formulario (DD/MM/YYYY H:MM:SS) a ISO."""
    if _es_vacio(raw):
        return None
    s = str(raw).strip()
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).isoformat(sep=' ', timespec='seconds')
        except ValueError:
            continue
    return s

def _resolver_par(cant_raw, est_raw):
    """Resuelve un par CANTIDAD+ESTILO (barril/botella).

    - Ambos vacíos → None (sin cambios, forward-fill).
    - Uno vacío → None (registro incompleto, se ignora).
    - Ambos llenos → (estilo_normalizado, cantidad_float).
    """
    if _es_vacio(cant_raw) and _es_vacio(est_raw):
        return None
    if _es_vacio(cant_raw) or _es_vacio(est_raw):
        return None
    estilo = _normalizar_estilo(est_raw)
    if not estilo or estilo == 'VACIO':
        return None
    cant = _to_float(cant_raw)
    if cant is None:
        return None
    return estilo, cant

def _resolver_ferm(prev, lit_raw, est_raw):
    """Resuelve el estado de un fermentador con forward-fill."""
    prev = prev or {'litros': 0.0, 'estilo': ''}
    if _es_vacio(lit_raw) and _es_vacio(est_raw):
        return dict(prev)  # sin cambios
    lit = _to_float(lit_raw) if not _es_vacio(lit_raw) else None
    estilo = _normalizar_estilo(est_raw) if not _es_vacio(est_raw) else None
    if estilo == 'VACIO':
        return {'litros': 0.0, 'estilo': ''}  # tanque vaciado explícito
    if estilo is None:
        estilo = prev['estilo']
    if lit is None:
        lit = prev['litros']
    return {'litros': lit, 'estilo': estilo}

FERM_KEYS = ['F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7']

def procesar_historico(values):
    """Procesa TODAS las filas del Sheet con forward-fill.

    Devuelve (historial, fermentadores, barriles, botellas, fecha):
      - historial: lista de snapshots diarios [{fecha, fermentadores, barriles, botellas}]
      - fermentadores / barriles / botellas / fecha: estado resuelto del ÚLTIMO registro.
    """
    filas = [f for f in values[1:] if f]

    def _clave_temporal(f):
        raw = f[0] if len(f) > 0 else ''
        return _normalizar_fecha(raw) or ''

    filas.sort(key=_clave_temporal)

    ferm_state = {}
    barril_state = {}
    botella_state = {}
    historial = []

    for fila in filas:
        fecha = _normalizar_fecha(fila[0]) if len(fila) > 0 else None

        # Fermentadores F1..F7 (columnas 1..14)
        for i, key in enumerate(FERM_KEYS):
            lit_raw = fila[1 + i * 2] if len(fila) > 1 + i * 2 else ''
            est_raw = fila[2 + i * 2] if len(fila) > 2 + i * 2 else ''
            ferm_state[key] = _resolver_ferm(ferm_state.get(key), lit_raw, est_raw)

        # Barriles (columnas 15..28) — acumular por estilo si se repite en la fila
        row_barril = {}
        for i in range(15, 29, 2):
            if len(fila) > i + 1:
                r = _resolver_par(fila[i], fila[i + 1])
                if r:
                    row_barril[r[0]] = row_barril.get(r[0], 0.0) + r[1]
        for e, c in row_barril.items():
            barril_state[e] = c

        # Botellas (columnas 29..40) — acumular por estilo si se repite en la fila
        row_botella = {}
        for i in range(29, 41, 2):
            if len(fila) > i + 1:
                r = _resolver_par(fila[i], fila[i + 1])
                if r:
                    row_botella[r[0]] = row_botella.get(r[0], 0.0) + r[1]
        for e, c in row_botella.items():
            botella_state[e] = c

        historial.append({
            'fecha': fecha,
            'fermentadores': {k: dict(v) for k, v in ferm_state.items()},
            'barriles': dict(barril_state),
            'botellas': dict(botella_state),
        })

    if not historial:
        return [], {}, {}, {}, None

    ultimo = historial[-1]
    return historial, dict(ferm_state), dict(barril_state), dict(botella_state), ultimo['fecha']

def leer_sheet_online():
    """Lee el Sheet completo y devuelve el estado resuelto + histórico con forward-fill.

    Devuelve (fermentadores, barriles, botellas, fecha, historial).
    """
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID_INVENTARIO}/values/A:AF?key={API_KEY}"
    resp = requests.get(url, timeout=15)
    if resp.status_code != 200:
        return None, None, None, None, []
    values = resp.json().get('values', [])
    if len(values) < 2:
        return None, None, None, None, []
    historial, ferm, barr, bot, fecha = procesar_historico(values)
    return ferm, barr, bot, fecha, historial

def consultar_alegra_online(dias=7):
    desde = (datetime.now() - timedelta(days=dias)).strftime('%Y-%m-%d')
    s = requests.Session()
    s.auth = (ALEGRA_EMAIL, ALEGRA_TOKEN)
    s.headers.update({'Accept': 'application/json'})
    salidas = defaultdict(lambda: {'botellas':0,'litros':0,'cop':0,'docs':0})

    for endpoint in ['invoices', 'bills']:
        for start in range(0,200,30):
            r = s.get(f'{ALEGRA_URL}{endpoint}', params={
                'start_date':desde,'limit':30,'start':start,'order_direction':'DESC'}, timeout=20)
            if r.status_code != 200: break
            data = r.json()
            docs = data if isinstance(data,list) else data.get('data',[])
            for doc in docs:
                for item in doc.get('items',[]):
                    # Intentar match por ID de Alegra o por itemReference
                    pid = str(item.get('id',''))
                    ref = str(item.get('itemReference', ''))
                    qty = float(item.get('quantity',1))
                    
                    estilo = ID_ALEGRA_ESTILO.get(pid) or ID_ALEGRA_ESTILO.get(ref)
                    if not estilo:
                        # Fallback: buscar por código PTB/PTL en itemReference
                        for e, cod in {**CODIGOS_BOTELLA, **CODIGOS_LITRO}.items():
                            if ref == cod:
                                estilo = e; break
                    
                    if estilo:
                        if pid in ID_ALEGRA_ES_BOTELLA:
                            salidas[estilo]['botellas'] += int(qty)
                            salidas[estilo]['litros'] += qty * BOTELLA_L
                        elif pid in ID_ALEGRA_ES_LITRO:
                            salidas[estilo]['litros'] += qty
                        salidas[estilo]['cop'] += float(item.get('price',0) or 0) * qty
            if len(docs) < 30: break
    return salidas

# ===================== LECTURA OFFLINE =====================
def leer_input_local():
    if os.path.exists(PLANTILLA_JSON):
        with open(PLANTILLA_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('fermentadores',{}), data.get('barriles',{}), data.get('botellas',{}), data.get('fecha','')
    elif os.path.exists(ULTIMO_INVENTARIO_JSON):
        with open(ULTIMO_INVENTARIO_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('fermentadores',{}), data.get('barriles',{}), data.get('botellas_producidas',{}), data.get('fecha','')
    return None, None, None, None

def _normalizar_estilo(raw):
    """Mapea nombres largos o códigos al estilo canónico (ESTILOS)."""
    if not raw: return None
    r = raw.strip().lower()
    if any(x in r for x in ['american india pale ale', 'vagabundo', 'ptl04', 'ptb04']): return 'IPA'
    if any(x in r for x in ['american pale ale', 'cienfuegos', 'ptl03', 'ptb03']): return 'APA'
    if any(x in r for x in ['golden ale', 'siempre viva', 'ptl01', 'ptb01']): return 'GOLDEN ALE'
    if any(x in r for x in ['irish red ale', 'mística', 'mistica', 'ptl02', 'ptb02']): return 'IRISH RED ALE'
    if any(x in r for x in ['stout', 'sangre negra', 'ptl05', 'ptb05']): return 'STOUT'
    if any(x in r for x in ['hidromiel', 'hidro']): return 'HIDROMIEL'
    if any(x in r for x in ['german pils']): return 'GERMAN PILS'
    if any(x in r for x in ['red ipa', 'red indian pale ale']): return 'RED IPA'
    if any(x in r for x in ['scottish', 'scottish ale']): return 'SCOTTISH'
    if r == 'vacio' or r == 'vacío': return 'VACIO'
    return None

def parsear_fila(last):
    """(Deprecado) Mantenido por compatibilidad. Usa procesar_historico()."""
    fermentadores = {}
    for i, key in enumerate(FERM_KEYS):
        lit_raw = last[1 + i * 2] if len(last) > 1 + i * 2 else ''
        est_raw = last[2 + i * 2] if len(last) > 2 + i * 2 else ''
        fermentadores[key] = _resolver_ferm(fermentadores.get(key), lit_raw, est_raw)

    barriles = defaultdict(float)
    for i in range(15, 29, 2):
        if len(last) > i + 1:
            r = _resolver_par(last[i], last[i + 1])
            if r:
                barriles[r[0]] += r[1]

    botellas = defaultdict(float)
    for i in range(29, 41, 2):
        if len(last) > i + 1:
            r = _resolver_par(last[i], last[i + 1])
            if r:
                botellas[r[0]] += r[1]

    fecha = _normalizar_fecha(last[0]) if last and not _es_vacio(last[0]) else datetime.now().strftime('%Y-%m-%d %H:%M')
    return fermentadores, barriles, botellas, fecha

# ===================== PLANTILLA =====================
def generar_plantilla():
    plantilla = {
        "modo": "LLENAR MANUALMENTE Y GUARDAR",
        "instrucciones": "Edita los valores y guarda. Luego ejecuta: python nucleo_de_inventario_v2.py --offline",
        "fecha": datetime.now().strftime('%Y-%m-%d %H:%M'),
        "fermentadores": {
            "F1": {"litros": 0, "estilo": "GOLDEN ALE"},
            "F2": {"litros": 0, "estilo": "IRISH RED ALE"},
            "F3": {"litros": 0, "estilo": "APA"},
            "F4": {"litros": 0, "estilo": "IPA"},
            "F5": {"litros": 0, "estilo": "IPA"},
            "F6": {"litros": 0, "estilo": "GOLDEN ALE"},
            "F7": {"litros": 0, "estilo": "STOUT"}
        },
        "barriles": {
            "GOLDEN ALE": 0, "IRISH RED ALE": 0, "APA": 0, "IPA": 0, "STOUT": 0
        },
        "botellas": {
            "GOLDEN ALE": 0, "IRISH RED ALE": 0, "APA": 0, "IPA": 0, "STOUT": 0
        },
        "ventas_manuales": {
            "GOLDEN ALE": {"botellas": 0, "litros": 0},
            "IRISH RED ALE": {"botellas": 0, "litros": 0},
            "APA": {"botellas": 0, "litros": 0},
            "IPA": {"botellas": 0, "litros": 0},
            "STOUT": {"botellas": 0, "litros": 0}
        }
    }

    # Si hay datos previos, cargarlos como valores por defecto
    if os.path.exists(ULTIMO_INVENTARIO_JSON):
        with open(ULTIMO_INVENTARIO_JSON, 'r', encoding='utf-8') as f:
            prev = json.load(f)
        for key, val in prev.get('fermentadores',{}).items():
            if key in plantilla['fermentadores']:
                plantilla['fermentadores'][key] = val
        for estilo in ESTILOS:
            if estilo in prev.get('barriles',{}):
                plantilla['barriles'][estilo] = prev['barriles'][estilo]
            if estilo in prev.get('botellas_producidas',{}):
                plantilla['botellas'][estilo] = prev['botellas_producidas'][estilo]

    with open(PLANTILLA_JSON, 'w', encoding='utf-8') as f:
        json.dump(plantilla, f, ensure_ascii=False, indent=2)
    print(f'✅ Plantilla generada: {PLANTILLA_JSON}')
    print('   Edítala manualmente y ejecuta: python nucleo_de_inventario_v2.py --offline')

# ===================== EXCEL =====================
def generar_excel(fermentadores, barriles, botellas_prod, fecha, salidas, modo='online'):
    litros_ferm = defaultdict(float)
    for key, data in fermentadores.items():
        litros_ferm[data['estilo']] += data['litros']

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    def sh(ws, row, ncols):
        for c in range(1, ncols+1):
            cell = ws.cell(row=row, column=c)
            cell.font = H_FONT; cell.fill = H_FILL; cell.alignment = CENTER; cell.border = BORDER

    def wr(ws, row, values, bold=False, fill=None):
        for c, v in enumerate(values, 1):
            cell = ws.cell(row=row, column=c, value=v)
            cell.border = BORDER; cell.alignment = WRAP
            if bold: cell.font = Font(bold=True)
            if fill: cell.fill = fill

    # ── HOJA 1: INPUT MANUAL ──
    ws0 = wb.create_sheet('INPUT (llenar aqui)')
    ws0.merge_cells('A1:F1')
    ws0['A1'] = f'📝 ENTRADA MANUAL DE INVENTARIO — {fecha[:10]} — MODO: {modo.upper()}'
    ws0['A1'].font = T_FONT
    ws0['A2'] = 'Llena las celdas amarillas. Datos se guardan en plantilla_input_local.json'
    ws0['A2'].font = Font(italic=True, color='E67E22')

    # Fecha
    ws0.cell(row=4, column=1, value='Fecha:').font = Font(bold=True)
    ws0.cell(row=4, column=2, value=fecha[:10])
    ws0.cell(row=4, column=2).fill = INPUT_FILL; ws0.cell(row=4, column=2).border = BORDER

    # Fermentadores
    sh(ws0, 6, 4)
    wr(ws0, 6, ['Fermentador','Capacidad','Litros (editar)','Estilo (editar)'])
    for i, nombre in enumerate(NOMBRES_FERM):
        r = 7 + i
        key = f'F{i+1}'
        data = fermentadores.get(key, {'litros':0,'estilo':''})
        ws0.cell(row=r,column=1,value=nombre).border = BORDER
        ws0.cell(row=r,column=2,value=f'{CAPACIDADES[key]}L').border = BORDER
        ws0.cell(row=r,column=3,value=data['litros']).border = BORDER
        ws0.cell(row=r,column=3).fill = INPUT_FILL
        ws0.cell(row=r,column=4,value=data['estilo']).border = BORDER
        ws0.cell(row=r,column=4).fill = INPUT_FILL

    # Barriles y botellas
    r_base = 7 + 7 + 1
    sh(ws0, r_base, 4)
    wr(ws0, r_base, ['Estilo','Litros en Barril (editar)','Botellas producidas (editar)','Ventas botellas (editar)'])
    for i, estilo in enumerate(ESTILOS):
        r = r_base + 1 + i
        wr(ws0, r, [
            estilo,
            barriles.get(estilo, 0),
            botellas_prod.get(estilo, 0),
            int(salidas.get(estilo, {}).get('botellas', 0))
        ])
        ws0.cell(row=r, column=2).fill = INPUT_FILL
        ws0.cell(row=r, column=3).fill = INPUT_FILL
        ws0.cell(row=r, column=4).fill = INPUT_FILL

    for col, w in enumerate([22,14,14,22,20,20], 1):
        ws0.column_dimensions[get_column_letter(col)].width = w

    # ── HOJA 2: RESUMEN ──
    ws1 = wb.create_sheet('Resumen')
    ws1.merge_cells('A1:G1')
    ws1['A1'] = f'NÚCLEO DE INVENTARIO — {fecha[:10]} — {modo.upper()}'
    ws1['A1'].font = T_FONT; ws1['A1'].alignment = Alignment(horizontal='center')

    sh(ws1, 3, 7)
    wr(ws1, 3, ['Estilo','Litros Ferm.','Litros Barril','Ventas (L)','Total Litros','COP est.','Estado'])
    total_l = 0; total_cop = 0; tb = 0
    for i, estilo in enumerate(ESTILOS):
        r = 4 + i
        lf = litros_ferm.get(estilo,0)
        lb_input = barriles.get(estilo,0)
        lb_vendido = salidas.get(estilo,{}).get('litros',0)
        lb_final = max(0, lb_input - lb_vendido)
        be = 0
        tl = lf + lb_final + be
        cod = CODIGOS_LITRO.get(estilo,''); cop = tl * PRECIOS_LITRO.get(cod,0)
        estado = '⚠️ Sin barril' if lb_final == 0 and lf > 0 else '✅ OK'
        wr(ws1, r, [estilo, f'{lf:,.0f}', f'{lb_final:,.1f}', f'{lb_vendido:,.1f}', f'{tl:,.0f}', f'${cop:,.0f}', estado])
        total_l += tl; total_cop += cop; tb += lb_final
    wr(ws1, 4+5, ['TOTAL','','','',f'{total_l:,.0f}',f'${total_cop:,.0f}',''], bold=True)

    # Ventas
    rv = 11
    ws1.cell(row=rv, column=1, value='VENTAS DESCONTADAS').font = Font(bold=True, size=12)
    sh(ws1, rv+1, 4)
    wr(ws1, rv+1, ['Estilo','Botellas','Litros','COP'])
    tv = 0
    for i, estilo in enumerate(ESTILOS):
        s = salidas.get(estilo,{})
        cop_s = s.get('cop',0)
        wr(ws1, rv+2+i, [estilo, int(s.get('botellas',0)), f"{s.get('litros',0):.1f}", f'${cop_s:,.0f}'])
        tv += cop_s
    wr(ws1, rv+2+5, ['TOTAL','','',f'${tv:,.0f}'], bold=True)

    for col, w in enumerate([22,16,16,16,16,16], 1):
        ws1.column_dimensions[get_column_letter(col)].width = w

    # ── HOJA 3: FERMENTADORES ──
    ws2 = wb.create_sheet('Fermentadores')
    ws2.merge_cells('A1:G1')
    ws2['A1'] = f'FERMENTADORES — {fecha[:10]}'
    ws2['A1'].font = T_FONT
    sh(ws2, 3, 7)
    wr(ws2, 3, ['Fermentador','Cap.','Litros','%','Estilo','Alarma','Acción'])
    for i, nombre in enumerate(NOMBRES_FERM):
        r = 4 + i; key = f'F{i+1}'
        d = fermentadores.get(key,{'litros':0,'estilo':'?'})
        cap = CAPACIDADES[key]; lit = d['litros']; pct = lit/cap*100 if cap else 0
        alarma = '🔴 ENVASAR' if pct >= 95 else '🟡 Pronto' if pct >= 80 else '🟢 OK'
        accion = 'Envasar urgente' if pct >= 95 else 'Envasar pronto' if pct >= 80 else 'Monitorear'
        wr(ws2, r, [nombre, f'{cap}L', lit, f'{pct:.0f}%', d['estilo'], alarma, accion])
        ws2.cell(row=r,column=6).fill = RED if pct>=95 else YELLOW if pct>=80 else GREEN
    for col, w in enumerate([22,8,10,8,22,14,20], 1):
        ws2.column_dimensions[get_column_letter(col)].width = w

    # ── HOJA 4: BARRILES ──
    ws3 = wb.create_sheet('Barriles')
    ws3.merge_cells('A1:H1')
    ws3['A1'] = f'BARRILES — {fecha[:10]}'
    ws3['A1'].font = T_FONT
    sh(ws3, 3, 8)
    wr(ws3, 3, ['Estilo','Código','Litros INPUT','Ventas (L)','Litros FINAL','Barriles (58.55L)','COP','Estado'])
    tb = 0
    for i, estilo in enumerate(ESTILOS):
        r = 4 + i
        l_input = barriles.get(estilo, 0)
        l_vendido = salidas.get(estilo, {}).get('litros', 0)
        l_final = max(0, l_input - l_vendido)
        cod = CODIGOS_LITRO.get(estilo, '')
        cop = l_final * PRECIOS_LITRO.get(cod, 0)
        barriles_equiv = l_final / BARRIL_L
        estado = '🔴 Agotado' if l_final == 0 else '🟡 Bajo' if l_final < 30 else '🟢 OK'
        wr(ws3, r, [estilo, cod, f'{l_input:,.1f}', f'{l_vendido:,.1f}',
                     f'{l_final:,.1f}', f'{barriles_equiv:,.1f}', f'${cop:,.0f}', estado])
        if l_final == 0: ws3.cell(row=r, column=8).fill = RED
        elif l_final < 30: ws3.cell(row=r, column=8).fill = YELLOW
        tb += l_final
    wr(ws3, 4+5, ['TOTAL','','','',f'{tb:,.1f}','',f'${tb*18000:,.0f}',''], bold=True)
    for col, w in enumerate([22,10,12,10,12,14,14,12], 1):
        ws3.column_dimensions[get_column_letter(col)].width = w

    # ── HOJA 5: BOTELLAS ──
    ws4 = wb.create_sheet('Botellas')
    ws4.merge_cells('A1:H1')
    ws4['A1'] = f'BOTELLAS — {fecha[:10]}'
    ws4['A1'].font = T_FONT
    sh(ws4, 3, 8)
    wr(ws4, 3, ['Estilo','Código','Stock INPUT','Ventas (und)','Stock FINAL','Fondo','Disp. venta','Alarma'])
    for i, estilo in enumerate(ESTILOS):
        r = 4 + i
        stock_input = botellas_prod.get(estilo, 0)
        vendidas = int(salidas.get(estilo, {}).get('botellas', 0))
        stock_final = stock_input  # El INPUT ya es el stock actual (no es producción semanal necesariamente)
        disp = max(0, stock_final - FONDO_BOTELLAS - vendidas)
        alarma = '🔴 BAJO' if disp < UMBRAL_ALARMA_BAJO else '🟢 BIEN' if disp > 200 else '🟡 MEDIO'
        cod = CODIGOS_BOTELLA.get(estilo, '')
        wr(ws4, r, [estilo, cod, int(stock_input), vendidas, int(stock_final), FONDO_BOTELLAS, int(disp), alarma])
        ws4.cell(row=r, column=8).fill = RED if disp < UMBRAL_ALARMA_BAJO else YELLOW if disp < 200 else GREEN
    for col, w in enumerate([22,10,12,10,12,8,12,12], 1):
        ws4.column_dimensions[get_column_letter(col)].width = w

    wb.save(OUTPUT_EXCEL)
    return total_l, tb, tv

# ===================== MAIN =====================
def main():
    offline = '--offline' in sys.argv
    plantilla = '--plantilla' in sys.argv

    if plantilla:
        generar_plantilla()
        return

    print(f'🧬 NÚCLEO DE INVENTARIO v2 — {"OFFLINE" if offline else "ONLINE"}')
    print('='*50)

    if offline:
        print('\n📁 Modo OFFLINE — leyendo datos locales...')
        fermentadores, barriles, botellas, fecha = leer_input_local()
        historial = []
        if not fermentadores:
            print('❌ No hay datos locales. Ejecuta primero:')
            print('   python nucleo_de_inventario_v2.py --plantilla')
            print('   (Llena el JSON y vuelve a ejecutar con --offline)')
            return
        salidas = defaultdict(lambda: {'botellas':0,'litros':0,'cop':0,'docs':0})
        # Leer ventas manuales si existen
        if os.path.exists(PLANTILLA_JSON):
            with open(PLANTILLA_JSON) as f:
                p = json.load(f)
            for estilo, data in p.get('ventas_manuales',{}).items():
                salidas[estilo] = {'botellas':data.get('botellas',0), 'litros':data.get('litros',0), 'cop':0, 'docs':0}
        print(f'   ✅ Fermentadores: {sum(v["litros"] for v in fermentadores.values()):,.0f}L')
    else:
        if not hay_internet():
            print('\n⚠️ Sin conexión a internet. Cambiando a modo OFFLINE...')
            offline = True
            fermentadores, barriles, botellas, fecha = leer_input_local()
            historial = []
            if not fermentadores:
                print('❌ Sin datos locales tampoco. Genera la plantilla primero.')
                return
            salidas = defaultdict(lambda: {'botellas':0,'litros':0,'cop':0,'docs':0})
        else:
            print('\n📥 ONLINE — Google Sheet...')
            fermentadores, barriles, botellas, fecha, historial = leer_sheet_online()
            if not fermentadores:
                print('❌ No se pudo leer el Sheet.')
                return
            print(f'   ✅ {sum(v["litros"] for v in fermentadores.values()):,.0f}L en fermentadores')

            print('\n📤 ONLINE — Alegra ventas...')
            salidas = consultar_alegra_online(dias=7)
            print(f'   ✅ ${sum(s.get("cop",0) for s in salidas.values()):,.0f} en ventas')

    # Generar Excel
    print('\n📊 Generando Excel...')
    tl, tb, tv = generar_excel(fermentadores, barriles, botellas, fecha, salidas, 'offline' if offline else 'online')
    print(f'   ✅ {OUTPUT_EXCEL}')

    # Guardar último inventario para offline
    ultimo = {'fecha': fecha, 'fermentadores': fermentadores,
              'barriles': dict(barriles), 'botellas_producidas': dict(botellas),
              'totales': {'litros_fermentando': tl, 'litros_barril': tb, 'ventas_cop': tv}}
    with open(ULTIMO_INVENTARIO_JSON, 'w', encoding='utf-8') as f:
        json.dump(ultimo, f, ensure_ascii=False, indent=2)

    # Guardar histórico resuelto (forward-fill) para el ledger y trazabilidad
    if historial:
        with open(HISTORIAL_JSON, 'w', encoding='utf-8') as f:
            json.dump({'actualizado': datetime.now().isoformat(),
                       'fecha_autoritativa': 'marca_temporal',
                       'snapshots': historial}, f, ensure_ascii=False, indent=2)
        print(f'   ✅ {HISTORIAL_JSON} ({len(historial)} snapshots)')

    # Generar inventario_neto.json para madremonte-dashboard (con deducciones)
    try:
        inventario_neto = {
            "generado": datetime.now().isoformat(),
            "fecha_lectura": fecha,
            "fermentadores": [],
            "barriles": [],
            "botellas": [],
            "totales": {
                "litros_fermentando": int(tl),
                "litros_barril": int(tb),
                "ventas_cop": int(tv)
            }
        }
        CAPS = {'F1':400,'F2':1200,'F3':400,'F4':700,'F5':800,'F6':1000,'F7':500}
        for key in ['F1','F2','F3','F4','F5','F6','F7']:
            d = fermentadores.get(key, {'litros':0,'estilo':''})
            cap = CAPS.get(key, 400)
            inventario_neto['fermentadores'].append({
                'nombre': f'{key} Frankie' if key == 'F1' else f'{key} Igor' if key == 'F2' else
                          f'{key} Principito' if key == 'F3' else f'{key} Gargantua' if key == 'F4' else
                          f'{key} Pantagruel' if key == 'F5' else f'{key} Potter' if key == 'F6' else f'{key} HighLander',
                'estilo': d['estilo'],
                'litros': d['litros'],
                'capacidad': cap,
                'porcentaje': round(d['litros']/cap*100) if cap else 0
            })
        for estilo in ESTILOS:
            l_input = barriles.get(estilo, 0)
            l_vendido = salidas.get(estilo, {}).get('litros', 0)
            l_neto = max(0, l_input - l_vendido)
            inventario_neto['barriles'].append({
                'codigo': CODIGOS_LITRO.get(estilo, ''),
                'estilo': estilo,
                'litros': round(l_neto, 1)
            })
        for estilo in ESTILOS:
            b_input = botellas.get(estilo, 0)
            b_vendido = int(salidas.get(estilo, {}).get('botellas', 0))
            b_neto = max(0, b_input - b_vendido)
            inventario_neto['botellas'].append({
                'codigo': CODIGOS_BOTELLA.get(estilo, ''),
                'estilo': estilo,
                'cantidad': int(b_neto)
            })

        # Guardar en dashboard-maestro/data/inventario_neto.json
        dashboard_data = Path(
            os.environ.get("INVENTARIO_OUT", os.path.join(BASE_DIR, "..", "data", "inventario_neto.json"))
        )
        dashboard_data.parent.mkdir(parents=True, exist_ok=True)
        with open(dashboard_data, 'w', encoding='utf-8') as f:
            json.dump(inventario_neto, f, ensure_ascii=False, indent=2)
        print(f'   ✅ inventario_neto.json generado para dashboard-maestro')
    except Exception as e:
        print(f'   ⚠️  Error generando inventario_neto.json: {e}')

    # ── Integración con Ledger de Inventario ──
    try:
        from ledger_inventario import LedgerInventario
        ledger = LedgerInventario()
        if historial:
            ledger.actualizar_desde_historial(historial)
        else:
            ledger.actualizar_desde_nucleo(fermentadores, barriles, botellas, fecha)
        alertas = ledger.get_alertas()
        if alertas:
            print(f'\n🚨 ALERTAS DE INVENTARIO ({len(alertas)}):')
            for a in alertas:
                icono = '🔴' if a['urgencia'] == 'critica' else '🟠' if a['urgencia'] == 'alta' else '🟡'
                tipo = a['tipo']
                if tipo == 'EMBOTELLAR_PENDIENTE':
                    fds = a.get('fermentadores', [])
                    extra = f" (Fuente: {', '.join(fds)})" if fds else ""
                    print(f'  {icono} [{tipo}] {a["mensaje"]}{extra}')
                elif tipo == 'BOTELLAS_VACIAS':
                    print(f'  {icono} [{tipo}] {a["mensaje"]}')
                elif tipo == 'EMBARRILAR_PENDIENTE':
                    print(f'  {icono} [{tipo}] {a["mensaje"]}')
                elif tipo == 'COMPROMISO_PENDIENTE':
                    print(f'  {icono} [{tipo}] {a["mensaje"]}')
                else:
                    print(f'  {icono} [{tipo}] {a["mensaje"]}')
        else:
            print(f'\n✅ Sin alertas de inventario.')
    except Exception as e:
        print(f'\n⚠️  Error integrando ledger: {e}')

    print(f'\n✅ Núcleo actualizado. Ocupación: {tl/5000*100:.0f}%')
    if offline:
        print('📁 Datos guardados localmente. Puedes ver el Excel sin internet.')


if __name__ == '__main__':
    main()

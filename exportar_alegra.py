#!/usr/bin/env python3
"""Exporta facturas desde Alegra API a JSONs mensuales para el dashboard-maestro.
Usa limit=30 (maximo de Alegra) con 2s entre paginas (30/min, seguro para rate limit).
"""
import json, os, sys, time
import requests
from collections import defaultdict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
CATALOGO_PATH = os.path.join(SCRIPT_DIR, "catalogo.json")
os.makedirs(DATA_DIR, exist_ok=True)

AUTH = (os.environ.get("ALEGRA_EMAIL", ""), os.environ.get("ALEGRA_TOKEN", os.environ.get("ALEGRA_API_KEY", "")))
BASE = 'https://api.alegra.com/api/v1/invoices'
LIMIT = 30
SLEEP = 2.0  # 30 llamadas/min, bien dentro del limite de 60

MES_ES = {
    "January":"Enero","February":"Febrero","March":"Marzo","April":"Abril",
    "May":"Mayo","June":"Junio","July":"Julio","August":"Agosto",
    "September":"Septiembre","October":"Octubre","November":"Noviembre","December":"Diciembre"
}

MES_NUM = {
    "Enero":"01","Febrero":"02","Marzo":"03","Abril":"04",
    "Mayo":"05","Junio":"06","Julio":"07","Agosto":"08",
    "Septiembre":"09","Octubre":"10","Noviembre":"11","Diciembre":"12"
}

def fetch_all():
    """Descarga todas las facturas pagina por pagina."""
    facturas = []
    productos = []
    start = 0
    page = 0
    while True:
        r = None
        for intento in range(3):
            try:
                r = requests.get(BASE, auth=AUTH, params={
                    'start': start, 'limit': LIMIT,
                    'order_direction': 'DESC', 'order_field': 'date'
                }, timeout=30)
                r.raise_for_status()
                break
            except requests.exceptions.RequestException:
                if intento == 2:
                    raise
                time.sleep(5)
        data = r.json()
        items = data if isinstance(data, list) else data.get('data', [])
        if not items:
            break
        for inv in items:
            fecha = (inv.get("date") or "")[:10]
            facturas.append({
                "id": str(inv.get("id", "")),
                "cliente": inv.get("client", {}).get("name", "Cliente") or "Consumidor Final",
                "total": int(inv.get("total", 0)),
                "status": inv.get("status", "draft"),
                "fecha": fecha
            })
            for it in (inv.get("items") or []):
                productos.append({
                    "nombre": it.get("name") or "Sin nombre",
                    "cantidad": int(it.get("quantity") or 0),
                    "total": int(it.get("total") or 0),
                    "fecha": fecha
                })
        page += 1
        print(f"  Pag {page:3d} start={start:4d} → {len(items):2d} items (total={len(facturas)})", flush=True)
        if len(items) < LIMIT:
            break
        start += LIMIT
        time.sleep(SLEEP)
    return facturas, productos

def agrupar_por_mes(facturas):
    """Agrupa facturas por mes (YYYY-MM) y guarda JSONs."""
    meses = {}
    for f in facturas:
        key = f["fecha"][:7]  # YYYY-MM
        if key not in meses:
            meses[key] = []
        meses[key].append(f)

    exportados = {}
    for key, items in sorted(meses.items()):
        total = sum(i["total"] for i in items)
        drafts = sum(1 for i in items if i["status"] == "draft")
        drafts_monto = sum(i["total"] for i in items if i["status"] == "draft")
        archivo = f"data/facturas_{key}.json"
        ruta = os.path.join(SCRIPT_DIR, archivo)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "total": len(items),
                "monto": total,
                "drafts": drafts,
                "drafts_monto": drafts_monto,
                "facturas": items
            }, f, ensure_ascii=False, indent=2)
        exportados[key] = archivo
        print(f"  ✅ {archivo}: {len(items)} fact, ${total:,} COP, {drafts} drafts", flush=True)
    return exportados

def actualizar_catalogo(exportados):
    with open(CATALOGO_PATH, "r", encoding="utf-8") as f:
        catalogo = json.load(f)
    for p in catalogo["periodos"]:
        partes = p["mes"].split()
        if len(partes) < 2:
            continue
        nombre_mes = partes[0]
        anio = partes[-1]
        mes = MES_NUM.get(nombre_mes)
        if not anio or not mes:
            continue
        key = f"{anio}-{mes}"
        if key not in exportados:
            continue
        # No sobreescribir facturación "rica" (con campos extra como total_facturas)
        fact_actual = p.get("facturacion")
        if fact_actual is not None and set(fact_actual.keys()) - {"archivo"}:
            print(f"  ↪ {p['mes']}: facturación con campos extra, se preserva", flush=True)
            continue
        p["facturacion"] = {"archivo": exportados[key]}
        print(f"  📋 catalogo: {p['mes']} → {exportados[key]}", flush=True)
    catalogo["actualizado"] = datetime.now().strftime("%Y-%m-%d")
    with open(CATALOGO_PATH, "w", encoding="utf-8") as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=2)

def generar_resumen_anual(facturas, productos):
    """Genera data/resumen_alegra.json con agregaciones del año en curso."""
    anio = datetime.now().year
    facturas_anio = [f for f in facturas if f["fecha"].startswith(str(anio))]
    productos_anio = [p for p in productos if p["fecha"].startswith(str(anio))]

    por_mes = defaultdict(lambda: {"total": 0, "count": 0})
    por_cliente = defaultdict(lambda: {"total": 0, "count": 0})
    por_mes_bar = defaultdict(lambda: {"total": 0, "count": 0})
    por_mes_externo = defaultdict(lambda: {"total": 0, "count": 0})
    for f in facturas_anio:
        por_mes[f["fecha"][:7]]["total"] += f["total"]
        por_mes[f["fecha"][:7]]["count"] += 1
        por_cliente[f["cliente"]]["total"] += f["total"]
        por_cliente[f["cliente"]]["count"] += 1
        if f["cliente"] == "Consumidor Final":
            por_mes_bar[f["fecha"][:7]]["total"] += f["total"]
            por_mes_bar[f["fecha"][:7]]["count"] += 1
        else:
            por_mes_externo[f["fecha"][:7]]["total"] += f["total"]
            por_mes_externo[f["fecha"][:7]]["count"] += 1

    por_producto = defaultdict(lambda: {"total": 0, "unidades": 0})
    por_mes_domicilio = defaultdict(lambda: {"total": 0, "count": 0})
    for p in productos_anio:
        por_producto[p["nombre"]]["total"] += p["total"]
        por_producto[p["nombre"]]["unidades"] += p["cantidad"]
        if "domicilio" in p["nombre"].lower():
            por_mes_domicilio[p["fecha"][:7]]["total"] += p["total"]
            por_mes_domicilio[p["fecha"][:7]]["count"] += p["cantidad"]

    total_anual = sum(f["total"] for f in facturas_anio)
    num_facturas = len(facturas_anio)

    resumen = {
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "anio": anio,
        "kpis": {
            "total_anual": total_anual,
            "num_facturas": num_facturas,
            "ticket_promedio": round(total_anual / num_facturas) if num_facturas else 0,
        },
        "por_mes": {k: dict(v) for k, v in sorted(por_mes.items())},
        "por_mes_bar": {k: dict(v) for k, v in sorted(por_mes_bar.items())},
        "por_mes_externo": {k: dict(v) for k, v in sorted(por_mes_externo.items())},
        "por_mes_factura": {k: {"total": v["total"] - por_mes_domicilio.get(k, {}).get("total", 0), "count": v["count"]} for k, v in sorted(por_mes.items())},
        "por_mes_domicilio": {k: dict(v) for k, v in sorted(por_mes_domicilio.items())},
        "por_producto": {k: dict(v) for k, v in sorted(por_producto.items(), key=lambda x: -x[1]["total"])},
        "por_cliente": {k: dict(v) for k, v in sorted(por_cliente.items(), key=lambda x: -x[1]["total"])},
    }

    ruta = os.path.join(DATA_DIR, "resumen_alegra.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)
    print(f"  ✅ resumen_alegra.json: {num_facturas} facturas, ${total_anual:,} COP, {len(por_producto)} productos", flush=True)

def main():
    print(f"📡 Descargando facturas de Alegra API...", flush=True)
    facturas, productos = fetch_all()
    if not facturas:
        print("❌ No se descargó ninguna factura de Alegra. Revisa ALEGRA_EMAIL/ALEGRA_TOKEN.", flush=True)
        sys.exit(1)
    print(f"\n📦 {len(facturas)} facturas descargadas. Agrupando por mes...", flush=True)
    exportados = agrupar_por_mes(facturas)
    print(f"\n📋 Actualizando catalogo.json...", flush=True)
    actualizar_catalogo(exportados)
    print(f"\n📊 Generando resumen anual...", flush=True)
    generar_resumen_anual(facturas, productos)
    print(f"\n✅ Listo: {len(exportados)} meses exportados", flush=True)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Genera data/pendientes_por_mes.json con las facturas "por cobrar" (status=open)
de Alegra agrupadas por mes (año en curso). Cada mes es plegable en el dashboard.
"""
import json
import os
import time

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

AUTH = (
    os.environ.get("ALEGRA_EMAIL", ""),
    os.environ.get("ALEGRA_TOKEN", os.environ.get("ALEGRA_API_KEY", "")),
)
BASE = "https://api.alegra.com/api/v1/invoices"
LIMIT = 30
SLEEP = 1.0

MES_ES = {
    "01": "Enero", "02": "Febrero", "03": "Marzo", "04": "Abril",
    "05": "Mayo", "06": "Junio", "07": "Julio", "08": "Agosto",
    "09": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre",
}


def fetch_open():
    """Descarga todas las facturas en estado open (por cobrar)."""
    facturas = []
    start = 0
    while True:
        r = None
        for intento in range(3):
            try:
                r = requests.get(
                    BASE, auth=AUTH,
                    params={
                        "status": "open", "start": start, "limit": LIMIT,
                        "order_direction": "DESC", "order_field": "id",
                    },
                    timeout=30,
                )
                r.raise_for_status()
                break
            except requests.exceptions.RequestException:
                if intento == 2:
                    raise
                time.sleep(5)
        data = r.json()
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            break
        for inv in items:
            nt = inv.get("numberTemplate") or {}
            facturas.append({
                "numero": nt.get("fullNumber") or str(inv.get("id", "")),
                "cliente": (inv.get("client") or {}).get("name", "") or "Consumidor Final",
                "fecha": (inv.get("date") or "")[:10],
                "total": inv.get("total", 0),
                "balance": inv.get("balance", 0),
            })
        if len(items) < LIMIT:
            break
        start += LIMIT
        time.sleep(SLEEP)
    return facturas


def main():
    anio = str(__import__("datetime").datetime.now().year)
    facturas = fetch_open()

    # Agrupar por mes (solo el año en curso)
    meses = {}
    for f in facturas:
        key = f["fecha"][:7]
        if key.startswith(anio):
            meses.setdefault(key, []).append(f)

    meses_ordenados = []
    for key in sorted(meses.keys(), reverse=True):
        items = sorted(meses[key], key=lambda x: str(x["numero"]), reverse=True)
        _, mes = key.split("-")
        meses_ordenados.append({
            "mes": key,
            "label": f"{MES_ES.get(mes, mes)} {anio}",
            "count": len(items),
            "monto": sum(i["balance"] or 0 for i in items),
            "facturas": items,
        })

    salida = {
        "generado": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "anio": anio,
        "total_abiertas": len(facturas),
        "total_anio": sum(m["count"] for m in meses_ordenados),
        "meses": meses_ordenados,
    }

    ruta = os.path.join(DATA_DIR, "pendientes_por_mes.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    print(
        f"✅ pendientes_por_mes.json: {salida['total_anio']} facturas {anio} "
        f"en {len(meses_ordenados)} meses (total abiertas: {salida['total_abiertas']})",
        flush=True,
    )


if __name__ == "__main__":
    main()

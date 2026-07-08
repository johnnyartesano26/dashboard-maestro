"""
Script para actualizar clientes_mensuales.json desde Google Sheets.
Ejecutar: python update_clientes.py
"""

import csv
import json
from collections import defaultdict
from pathlib import Path
import urllib.request

SHEET_ID = "1WFq09-LDg4le6FqC9BnBZfKZXSmb8Kn195wnFZaEMys"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
OUT_DIR = Path(__file__).resolve().parent.parent / "data"


def main():
    OUT_DIR.mkdir(exist_ok=True)

    # 1. Descargar CSV desde Google Sheets
    print(f"Descargando: {CSV_URL}")
    csv_path = OUT_DIR / "consolidado_ventas.csv"
    urllib.request.urlretrieve(CSV_URL, csv_path)

    # 2. Leer CSV
    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"Filas descargadas: {len(rows)}")

    # 3. Procesar datos
    clientes_data = []
    for r in rows:
        fecha = r.get("Fecha", "").strip()
        if not fecha:
            continue
        cliente = r.get("Nombre de cliente", "").strip()
        if not cliente:
            continue
        factura = r.get("Número de factura", "").strip()
        valor_str = r.get("Valor de la factura", "").strip()

        try:
            valor = float(valor_str.replace(".", "").replace(",", "."))
        except ValueError:
            valor = 0

        # Extraer mes
        parts = fecha.split("/")
        if len(parts) == 3:
            dia, mes, año = parts
            if len(año) == 2:
                año = "20" + año
            nombres = {
                1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
                5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
                9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
            }
            mes_label = f"{nombres.get(int(mes), mes)} {año}"
            mes_ordinal = f"{año}-{int(mes):02d}"
        else:
            mes_label = "Sin fecha"
            mes_ordinal = "0000-00"

        clientes_data.append({
            "fecha": fecha,
            "mes": mes_label,
            "mes_ordinal": mes_ordinal,
            "cliente": cliente,
            "factura": factura,
            "valor": valor,
        })

    # 4. Agrupar por cliente y mes
    agrupado = defaultdict(lambda: defaultdict(lambda: {"facturas": [], "total": 0}))
    for c in clientes_data:
        entry = agrupado[c["cliente"]][c["mes"]]
        entry["facturas"].append({"numero": c["factura"], "valor": c["valor"], "fecha": c["fecha"]})
        entry["total"] += c["valor"]

    resultado = []
    for cliente, meses in sorted(agrupado.items()):
        obj = {
            "cliente": cliente,
            "total_general": sum(m["total"] for m in meses.values()),
            "meses": {},
        }
        for mes, datos in sorted(meses.items()):
            datos["facturas"].sort(key=lambda f: f["fecha"])
            obj["meses"][mes] = datos
        resultado.append(obj)

    # 5. Guardar JSON
    json_path = OUT_DIR / "clientes_mensuales.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    total = sum(c["total_general"] for c in resultado)
    print(f"Clientes: {len(resultado)}")
    print(f"Total facturado: ${total:,.0f} COP")
    print(f"JSON generado: {json_path}")


if __name__ == "__main__":
    main()

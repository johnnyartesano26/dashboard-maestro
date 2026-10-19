#!/usr/bin/env python3
"""
ledger_inventario.py — Libro Mayor de Inventario (3 capas).
Mantiene el registro cronológico de todas las entradas, salidas y compromisos
del inventario de Madre Monte.

Capas:
  1. FERMENTADOR — litros en proceso (no vendible)
  2. BARRIL       — litros de producto terminado a granel (vendible por litro)
  3. BOTELLA      — unidades de producto terminado (vendible por unidad)

Insumos:
  - botellas_vacias_limpias (80 cajas × 24 und = 1,920 por pedido)

Uso:
  from ledger_inventario import LedgerInventario
  ledger = LedgerInventario()
  ledger.registrar_entrada("2026-07-29", "IPA", "barril_litros", 88.0, "Delta semanal")
  disponible = ledger.calcular_disponible("IPA", "barril")
  puede, razon = ledger.puedo_despachar("IPA", botellas=50, litros=0)
"""

import json
import os
import shutil
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────
LEDGER_DIR = Path(__file__).resolve().parent
LEDGER_PATH = LEDGER_DIR / "ledger_inventario.json"
INSUMOS_PATH = LEDGER_DIR / "insumos.json"
DASHBOARD_DATA = Path("/mnt/c/Users/USUARIO/dashboard-maestro/data")

ESTILOS = ["GOLDEN ALE", "IRISH RED ALE", "APA", "IPA", "STOUT", "GERMAN PILS", "HIDROMIEL", "RED IPA", "SCOTTISH"]

BARRIL_L = 58.55
BOTELLA_L = 0.330

# Límites para alertas
UMBRAL_BAJO_BOTELLA = 120
UMBRAL_BAJO_BARRIL = 30
UMBRAL_FERMENTADOR_LISTO = 80  # % — listo para envasar
UMBRAL_DESBALANCE = 5.0  # litros — alerta de balance de masas

FERM_NAMES = {
    "F1": "F1 Frankie", "F2": "F2 Igor", "F3": "F3 Principito",
    "F4": "F4 Gargantua", "F5": "F5 Pantagruel", "F6": "F6 Potter",
    "F7": "F7 HighLander",
}
FERM_CAPACIDADES = {"F1": 400, "F2": 1200, "F3": 400, "F4": 700, "F5": 800, "F6": 1000, "F7": 500}


# ── Estructura inicial ──────────────────────────────────────────────

def _ledger_vacio():
    return {
        "version": "2.0",
        "actualizado": datetime.now().isoformat(),
        "movimientos": [],
        "fermentadores": {
            f"F{i}": {"nombre": name, "estilo": "", "litros": 0, "capacidad": cap, "porcentaje": 0}
            for i, (name, cap) in enumerate(zip(FERM_NAMES.values(), FERM_CAPACIDADES.values()), 1)
        },
        "saldos": {
            "fermentador": {
                e: {"litros": 0, "fermentadores": [], "pct_max": 0, "alerta": "verde"}
                for e in ESTILOS
            },
            "barril": {
                e: {"litros": 0, "comprometido": 0, "disponible": 0}
                for e in ESTILOS
            },
            "botella": {
                e: {"unidades": 0, "comprometido": 0, "disponible": 0}
                for e in ESTILOS
            },
        },
        "insumos": {
            "botellas_vacias_limpias": {
                "stock": 0, "unidades_por_pedido": 1920,
                "estado": "AGOTADO",
            },
        },
        "cronograma": [],
        "alertas": [],
    }


# ── Clase principal ─────────────────────────────────────────────────

class LedgerInventario:
    def __init__(self):
        self.data = self._cargar()
        self.insumos = self._cargar_insumos()
        self._contador_mov = len(self.data.get("movimientos", [])) + 1

    # ── Carga / Guardado ──────────────────────────────────────────

    def _cargar(self):
        if LEDGER_PATH.exists():
            try:
                with open(LEDGER_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "version" in data:
                    if "fermentadores" not in data:
                        data["fermentadores"] = _ledger_vacio()["fermentadores"]
                    for estilo in ESTILOS:
                        if estilo not in data["saldos"].get("fermentador", {}):
                            data["saldos"]["fermentador"][estilo] = {"litros": 0, "fermentadores": [], "pct_max": 0, "alerta": "roja"}
                        if estilo not in data["saldos"].get("barril", {}):
                            data["saldos"]["barril"][estilo] = {"litros": 0, "comprometido": 0, "disponible": 0}
                        if estilo not in data["saldos"].get("botella", {}):
                            data["saldos"]["botella"][estilo] = {"unidades": 0, "comprometido": 0, "disponible": 0}
                    self._populate_fermentadores_from_ultimo(data)
                    return data
            except Exception:
                pass
        return _ledger_vacio()

    def _populate_fermentadores_from_ultimo(self, data):
        """Carga los fermentadores desde ultimo_inventario_local.json si el ledger está vacío."""
        total_litros = sum(f.get("litros", 0) for f in data.get("fermentadores", {}).values())
        if total_litros > 0:
            return  # Ya tiene datos, no sobreescribir
        ultimo_path = LEDGER_DIR / "ultimo_inventario_local.json"
        if not ultimo_path.exists():
            return
        try:
            with open(ultimo_path, "r", encoding="utf-8") as f:
                ultimo = json.load(f)
            for fkey, fdata in ultimo.get("fermentadores", {}).items():
                if fkey in data.get("fermentadores", {}):
                    estilo_raw = fdata.get("estilo", "")
                    estilo = self._normalizar_estilo(estilo_raw) or estilo_raw
                    cap = FERM_CAPACIDADES.get(fkey, 400)
                    litros = fdata.get("litros", 0)
                    data["fermentadores"][fkey] = {
                        "nombre": FERM_NAMES.get(fkey, fkey),
                        "estilo": estilo,
                        "litros": litros,
                        "capacidad": cap,
                        "porcentaje": round(litros / cap * 100) if cap else 0,
                    }
        except Exception:
            pass

    def _guardar(self):
        self.data["actualizado"] = datetime.now().isoformat()
        LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        with open(LEDGER_PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        self._sync_dashboard()

    def _sync_dashboard(self):
        destinos = [
            Path("/mnt/c/Users/USUARIO/dashboard-maestro/data"),
            Path("/mnt/c/Users/USUARIO/madremonte-dashboard/data"),
        ]
        for destino in destinos:
            try:
                destino.mkdir(parents=True, exist_ok=True)
                shutil.copy(LEDGER_PATH, destino / "ledger_inventario.json")
            except Exception:
                pass

    def _cargar_insumos(self):
        if INSUMOS_PATH.exists():
            try:
                with open(INSUMOS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"botellas_vacias_limpias": {"stock": 0, "unidades_por_pedido": 1920, "estado": "AGOTADO"}}

    def _guardar_insumos(self):
        self.insumos["actualizado"] = datetime.now().strftime("%Y-%m-%d")
        with open(INSUMOS_PATH, "w", encoding="utf-8") as f:
            json.dump(self.insumos, f, ensure_ascii=False, indent=2)

    # ── Movimientos ────────────────────────────────────────────────

    def _next_id(self):
        mid = f"mov_{self._contador_mov:04d}"
        self._contador_mov += 1
        return mid

    def registrar_entrada(self, fecha, estilo, capa, cantidad, origen, nota="", fermentador_key=None):
        if estilo not in ESTILOS:
            estilo = self._normalizar_estilo(estilo)
        if estilo not in ESTILOS or cantidad <= 0:
            return

        mov = {
            "id": self._next_id(),
            "fecha": fecha,
            "tipo": "ENTRADA",
            "origen": origen,
            "estilo": estilo,
            "capa": capa,
            "cantidad": round(cantidad, 1),
            "nota": nota,
        }

        if capa == "barril_litros":
            if estilo not in self.data["saldos"]["barril"]:
                self.data["saldos"]["barril"][estilo] = {"litros": 0, "comprometido": 0, "disponible": 0}
            self.data["saldos"]["barril"][estilo]["litros"] = round(
                self.data["saldos"]["barril"][estilo]["litros"] + cantidad, 1
            )
            mov["saldo_capa"] = self.data["saldos"]["barril"][estilo]["litros"]
        elif capa == "botella_und":
            if estilo not in self.data["saldos"]["botella"]:
                self.data["saldos"]["botella"][estilo] = {"unidades": 0, "comprometido": 0, "disponible": 0}
            self.data["saldos"]["botella"][estilo]["unidades"] += int(cantidad)
            mov["saldo_capa"] = self.data["saldos"]["botella"][estilo]["unidades"]
        elif capa == "fermentador_litros":
            self.data["saldos"]["fermentador"][estilo]["litros"] = round(cantidad, 1)
            mov["saldo_capa"] = self.data["saldos"]["fermentador"][estilo]["litros"]
            mov["nota"] = nota
            if fermentador_key and fermentador_key in self.data.get("fermentadores", {}):
                self.data["fermentadores"][fermentador_key]["litros"] = round(cantidad, 1)
                self.data["fermentadores"][fermentador_key]["estilo"] = estilo
                cap = self.data["fermentadores"][fermentador_key]["capacidad"]
                self.data["fermentadores"][fermentador_key]["porcentaje"] = round(cantidad / cap * 100) if cap else 0

        self.data["movimientos"].append(mov)
        self._recalcular_disponibles()
        self._generar_alertas()
        self._guardar()

    def registrar_salida(self, fecha, estilo, capa, cantidad, origen, nota=""):
        if estilo not in ESTILOS:
            estilo = self._normalizar_estilo(estilo)
        if estilo not in ESTILOS or cantidad <= 0:
            return

        mov = {
            "id": self._next_id(),
            "fecha": fecha,
            "tipo": "SALIDA",
            "origen": origen,
            "estilo": estilo,
            "capa": capa,
            "cantidad": round(-cantidad, 1),
            "nota": nota,
        }

        if capa == "barril_litros":
            self.data["saldos"]["barril"][estilo]["litros"] = max(0, round(
                self.data["saldos"]["barril"][estilo]["litros"] - cantidad, 1
            ))
            # Liberar compromiso si habia
            self.data["saldos"]["barril"][estilo]["comprometido"] = max(0,
                self.data["saldos"]["barril"][estilo]["comprometido"] - cantidad)
            mov["saldo_capa"] = self.data["saldos"]["barril"][estilo]["litros"]
        elif capa == "botella_und":
            self.data["saldos"]["botella"][estilo]["unidades"] = max(0,
                int(self.data["saldos"]["botella"][estilo]["unidades"] - cantidad))
            self.data["saldos"]["botella"][estilo]["comprometido"] = max(0,
                self.data["saldos"]["botella"][estilo]["comprometido"] - cantidad)
            mov["saldo_capa"] = self.data["saldos"]["botella"][estilo]["unidades"]

        self.data["movimientos"].append(mov)
        self._recalcular_disponibles()
        self._generar_alertas()
        self._guardar()

    def comprometer_pedido(self, fecha, estilo, botellas, litros_barril, pedido_id, cliente, nota=""):
        if estilo not in ESTILOS:
            estilo = self._normalizar_estilo(estilo)
        if estilo not in ESTILOS:
            return False, f"Estilo '{estilo}' no reconocido"

        # Verificar disponibilidad
        puede, razon = self.puede_despachar(estilo, botellas=botellas, litros=litros_barril)

        for capa, cantidad in [("botella_und", botellas), ("barril_litros", litros_barril)]:
            if cantidad <= 0:
                continue
            mov = {
                "id": self._next_id(),
                "fecha": fecha,
                "tipo": "COMPROMISO",
                "origen": pedido_id,
                "estilo": estilo,
                "capa": capa,
                "cantidad": round(-cantidad, 1),
                "cliente": cliente,
                "nota": nota,
                "estado": "OK" if puede else "PENDIENTE_PRODUCCION",
            }
            if capa == "barril_litros":
                self.data["saldos"]["barril"][estilo]["comprometido"] = round(
                    self.data["saldos"]["barril"][estilo]["comprometido"] + cantidad, 1
                )
                mov["saldo_comprometido"] = self.data["saldos"]["barril"][estilo]["comprometido"]
            elif capa == "botella_und":
                self.data["saldos"]["botella"][estilo]["comprometido"] += int(cantidad)
                mov["saldo_comprometido"] = self.data["saldos"]["botella"][estilo]["comprometido"]

            self.data["movimientos"].append(mov)

        self._recalcular_disponibles()
        self._generar_alertas()
        self._guardar()

        return puede, razon

    # ── EMBARRILAR ───────────────────────────────────────────────

    def embarrilar(self, fecha, fermentador_key, litros, nota=""):
        """
        Transfiere litros de un fermentador a barril.
        Descuenta del fermentador, suma a barril, evalúa alarma 20%.
        """
        if fermentador_key not in self.data.get("fermentadores", {}):
            return False, f"Fermentador {fermentador_key} no existe"

        ferm = self.data["fermentadores"][fermentador_key]
        if ferm["litros"] < litros:
            return False, f"{ferm['nombre']} solo tiene {ferm['litros']:.1f}L, insuficiente para embarrilar {litros:.1f}L"

        estilo = ferm["estilo"]
        if not estilo or estilo not in ESTILOS:
            return False, f"El fermentador {fermentador_key} no tiene un estilo válido asignado"

        litros = round(litros, 1)

        # Descontar de fermentador
        ferm["litros"] = round(ferm["litros"] - litros, 1)
        ferm["porcentaje"] = round(ferm["litros"] / ferm["capacidad"] * 100) if ferm["capacidad"] else 0

        # Sumar a barril
        if estilo not in self.data["saldos"]["barril"]:
            self.data["saldos"]["barril"][estilo] = {"litros": 0, "comprometido": 0, "disponible": 0}
        self.data["saldos"]["barril"][estilo]["litros"] = round(
            self.data["saldos"]["barril"][estilo]["litros"] + litros, 1
        )

        # Actualizar saldo agregado de fermentador
        self.data["saldos"]["fermentador"][estilo]["litros"] = round(
            sum(f["litros"] for f in self.data["fermentadores"].values()
                if f["estilo"] == estilo), 1
        )

        mov = {
            "id": self._next_id(),
            "fecha": fecha,
            "tipo": "EMBARRILAR",
            "origen": fermentador_key,
            "estilo": estilo,
            "capa": "barril_litros",
            "cantidad": litros,
            "nota": nota or f"Embarrilado desde {ferm['nombre']}: {litros}L → barril {estilo}",
            "fermentador_restante": ferm["litros"],
            "barril_saldo": self.data["saldos"]["barril"][estilo]["litros"],
        }
        self.data["movimientos"].append(mov)

        self._recalcular_disponibles()
        self._generar_alertas()
        self._guardar()
        return True, f"Embarrilado {litros:.1f}L de {estilo} desde {ferm['nombre']}. Quedan {ferm['litros']:.1f}L en fermentador."

    # ── EMBOTELLAR ───────────────────────────────────────────────

    def embotellar(self, fecha, estilo, botellas, origen="barril", fermentador_key=None, nota=""):
        """
        Embotella desde barril o directamente desde fermentador.
        - origen='barril': descuenta litros del barril (botellas × 0.330L).
          Si el barril se agota, el excedente se descuenta del fermentador del estilo.
        - origen='fermentador': descuenta litros directamente del fermentador indicado.
        Siempre suma botellas al inventario de botellas.
        """
        if estilo not in ESTILOS:
            estilo = self._normalizar_estilo(estilo) or estilo
        if estilo not in ESTILOS:
            return False, f"Estilo '{estilo}' no reconocido"

        litros_necesarios = round(botellas * BOTELLA_L, 1)
        litros_descontados = 0
        fermentador_usado = None
        detalle = []

        if origen == "barril":
            barril_disp = self.data["saldos"]["barril"][estilo]["litros"]
            if barril_disp >= litros_necesarios:
                self.data["saldos"]["barril"][estilo]["litros"] = round(barril_disp - litros_necesarios, 1)
                litros_descontados = litros_necesarios
                detalle.append(f"{litros_necesarios:.1f}L desde barril")
            else:
                if barril_disp > 0:
                    self.data["saldos"]["barril"][estilo]["litros"] = 0
                    litros_descontados = barril_disp
                    litros_necesarios = round(litros_necesarios - barril_disp, 1)
                    detalle.append(f"{barril_disp:.1f}L desde barril (agotado)")

                faltante = litros_necesarios
                fermentadores_estilo = [
                    (k, f) for k, f in self.data.get("fermentadores", {}).items()
                    if f["estilo"] == estilo and f["litros"] > 0
                ]
                fermentadores_estilo.sort(key=lambda x: x[1]["porcentaje"], reverse=True)

                for fkey, fdata in fermentadores_estilo:
                    if faltante <= 0:
                        break
                    tomar = min(faltante, fdata["litros"])
                    fdata["litros"] = round(fdata["litros"] - tomar, 1)
                    fdata["porcentaje"] = round(fdata["litros"] / fdata["capacidad"] * 100) if fdata["capacidad"] else 0
                    litros_descontados += tomar
                    faltante = round(faltante - tomar, 1)
                    fermentador_usado = fkey
                    detalle.append(f"{tomar:.1f}L desde {fdata['nombre']}")

        elif origen == "fermentador":
            if not fermentador_key:
                return False, "Debe especificar --fermentador para origen=fermentador"
            if fermentador_key not in self.data.get("fermentadores", {}):
                return False, f"Fermentador {fermentador_key} no existe"
            ferm = self.data["fermentadores"][fermentador_key]
            if ferm["litros"] < litros_necesarios:
                return False, f"{ferm['nombre']} solo tiene {ferm['litros']:.1f}L, necesita {litros_necesarios:.1f}L"
            ferm["litros"] = round(ferm["litros"] - litros_necesarios, 1)
            ferm["porcentaje"] = round(ferm["litros"] / ferm["capacidad"] * 100) if ferm["capacidad"] else 0
            litros_descontados = litros_necesarios
            fermentador_usado = fermentador_key
            detalle.append(f"{litros_necesarios:.1f}L desde {ferm['nombre']}")

        else:
            return False, f"Origen '{origen}' no válido. Use 'barril' o 'fermentador'"

        # Actualizar saldo agregado de fermentador
        self.data["saldos"]["fermentador"][estilo]["litros"] = round(
            sum(f["litros"] for f in self.data["fermentadores"].values()
                if f["estilo"] == estilo), 1
        )

        # Sumar botellas
        if estilo not in self.data["saldos"]["botella"]:
            self.data["saldos"]["botella"][estilo] = {"unidades": 0, "comprometido": 0, "disponible": 0}
        self.data["saldos"]["botella"][estilo]["unidades"] += int(botellas)

        mov = {
            "id": self._next_id(),
            "fecha": fecha,
            "tipo": "EMBOTELLAR",
            "origen": origen,
            "estilo": estilo,
            "capa": "botella_und",
            "cantidad": int(botellas),
            "litros_descontados": round(litros_descontados, 1),
            "nota": nota or "; ".join(detalle),
            "fermentador_usado": fermentador_usado,
            "botella_saldo": self.data["saldos"]["botella"][estilo]["unidades"],
        }
        self.data["movimientos"].append(mov)

        self._recalcular_disponibles()
        self._generar_alertas()
        self._guardar()
        return True, f"Embotellado {int(botellas)} und de {estilo}: " + "; ".join(detalle)

    # ── VENTA CON CASCADA ────────────────────────────────────────

    def vender_barril(self, fecha, estilo, litros, cliente="", nota=""):
        """Venta de barril a granel. Barril primero, fermentador si se agota."""
        if estilo not in ESTILOS:
            estilo = self._normalizar_estilo(estilo) or estilo
        if estilo not in ESTILOS:
            return False, f"Estilo '{estilo}' no reconocido"

        litros = round(litros, 1)
        litros_pendientes = litros
        detalle = []

        # Capa 1: barril
        barril_disp = self.data["saldos"]["barril"][estilo]["litros"]
        if barril_disp > 0:
            tomar = min(litros_pendientes, barril_disp)
            self.data["saldos"]["barril"][estilo]["litros"] = round(barril_disp - tomar, 1)
            self.data["saldos"]["barril"][estilo]["comprometido"] = max(0,
                self.data["saldos"]["barril"][estilo]["comprometido"] - tomar)
            litros_pendientes = round(litros_pendientes - tomar, 1)
            detalle.append(f"{tomar:.1f}L desde barril")

        # Capa 2: fermentador (si barril no alcanzó)
        if litros_pendientes > 0:
            fermentadores_estilo = [
                (k, f) for k, f in self.data.get("fermentadores", {}).items()
                if f["estilo"] == estilo and f["litros"] > 0
            ]
            fermentadores_estilo.sort(key=lambda x: x[1]["porcentaje"], reverse=True)
            for fkey, fdata in fermentadores_estilo:
                if litros_pendientes <= 0:
                    break
                tomar = min(litros_pendientes, fdata["litros"])
                fdata["litros"] = round(fdata["litros"] - tomar, 1)
                fdata["porcentaje"] = round(fdata["litros"] / fdata["capacidad"] * 100) if fdata["capacidad"] else 0
                litros_pendientes = round(litros_pendientes - tomar, 1)
                detalle.append(f"{tomar:.1f}L desde {fdata['nombre']} (fermentador)")

        if litros_pendientes > 0:
            return False, f"No hay suficiente {estilo}. Faltan {litros_pendientes:.1f}L."

        self.data["saldos"]["fermentador"][estilo]["litros"] = round(
            sum(f["litros"] for f in self.data["fermentadores"].values()
                if f["estilo"] == estilo), 1
        )

        mov = {
            "id": self._next_id(),
            "fecha": fecha,
            "tipo": "VENTA_BARRIL",
            "origen": "venta",
            "estilo": estilo,
            "capa": "barril_litros",
            "cantidad": -litros,
            "cliente": cliente,
            "nota": nota or "; ".join(detalle),
            "barril_saldo": self.data["saldos"]["barril"][estilo]["litros"],
        }
        self.data["movimientos"].append(mov)
        self._recalcular_disponibles()
        self._generar_alertas()
        self._guardar()
        return True, f"Vendido {litros:.1f}L de {estilo}: " + "; ".join(detalle)

    def vender_botella(self, fecha, estilo, unidades, cliente="", nota=""):
        """Venta de botellas. Botella → Barril → Fermentador."""
        if estilo not in ESTILOS:
            estilo = self._normalizar_estilo(estilo) or estilo
        if estilo not in ESTILOS:
            return False, f"Estilo '{estilo}' no reconocido"

        unidades = int(unidades)
        pendientes = unidades
        detalle = []

        # Capa 1: botellas
        if estilo not in self.data["saldos"]["botella"]:
            self.data["saldos"]["botella"][estilo] = {"unidades": 0, "comprometido": 0, "disponible": 0}
        bot_disp = self.data["saldos"]["botella"][estilo]["unidades"]
        if bot_disp > 0:
            tomar = min(pendientes, bot_disp)
            self.data["saldos"]["botella"][estilo]["unidades"] -= tomar
            self.data["saldos"]["botella"][estilo]["comprometido"] = max(0,
                self.data["saldos"]["botella"][estilo]["comprometido"] - tomar)
            pendientes -= tomar
            detalle.append(f"{tomar} und desde botellas")

        # Capa 2: barril (convertir a botellas)
        if pendientes > 0:
            barril_disp = self.data["saldos"]["barril"][estilo]["litros"]
            botellas_posibles = int(barril_disp / BOTELLA_L)
            if botellas_posibles > 0:
                tomar_bot = min(pendientes, botellas_posibles)
                litros_a_tomar = round(tomar_bot * BOTELLA_L, 1)
                self.data["saldos"]["barril"][estilo]["litros"] = round(barril_disp - litros_a_tomar, 1)
                pendientes -= tomar_bot
                detalle.append(f"{tomar_bot} und desde barril ({litros_a_tomar:.1f}L)")

        # Capa 3: fermentador (si ni botella ni barril alcanzaron)
        if pendientes > 0:
            litros_necesarios = round(pendientes * BOTELLA_L, 1)
            fermentadores_estilo = [
                (k, f) for k, f in self.data.get("fermentadores", {}).items()
                if f["estilo"] == estilo and f["litros"] > 0
            ]
            fermentadores_estilo.sort(key=lambda x: x[1]["porcentaje"], reverse=True)
            for fkey, fdata in fermentadores_estilo:
                if litros_necesarios <= 0:
                    break
                tomar = min(litros_necesarios, fdata["litros"])
                fdata["litros"] = round(fdata["litros"] - tomar, 1)
                fdata["porcentaje"] = round(fdata["litros"] / fdata["capacidad"] * 100) if fdata["capacidad"] else 0
                litros_necesarios = round(litros_necesarios - tomar, 1)
                detalle.append(f"{tomar:.1f}L desde {fdata['nombre']} (fermentador)")

            botellas_tomadas_ferm = int(round((pendientes * BOTELLA_L - litros_necesarios) / BOTELLA_L))
            pendientes = 0

        if pendientes > 0:
            return False, f"No hay suficiente {estilo}. Faltan {pendientes} botellas."

        self.data["saldos"]["fermentador"][estilo]["litros"] = round(
            sum(f["litros"] for f in self.data["fermentadores"].values()
                if f["estilo"] == estilo), 1
        )

        mov = {
            "id": self._next_id(),
            "fecha": fecha,
            "tipo": "VENTA_BOTELLA",
            "origen": "venta",
            "estilo": estilo,
            "capa": "botella_und",
            "cantidad": -unidades,
            "cliente": cliente,
            "nota": nota or "; ".join(detalle),
            "botella_saldo": self.data["saldos"]["botella"][estilo]["unidades"],
        }
        self.data["movimientos"].append(mov)
        self._recalcular_disponibles()
        self._generar_alertas()
        self._guardar()
        return True, f"Vendido {unidades} und de {estilo}: " + "; ".join(detalle)

    # ── Consultas ──────────────────────────────────────────────────

    def calcular_disponible(self, estilo=None, capa=None):
        self._recalcular_disponibles()
        if estilo and capa:
            capa_key = self._capa_key(capa)
            return self.data["saldos"][capa_key].get(estilo, {}).get("disponible", 0)
        if estilo:
            return {
                "barril_litros": self.data["saldos"]["barril"].get(estilo, {}).get("disponible", 0),
                "botella_und": self.data["saldos"]["botella"].get(estilo, {}).get("disponible", 0),
            }
        return self.data["saldos"]

    def puede_despachar(self, estilo, botellas=0, litros=0):
        if estilo not in ESTILOS:
            estilo = self._normalizar_estilo(estilo)
            if estilo not in ESTILOS:
                return False, f"Estilo '{estilo}' no reconocido"

        razones = []
        puede = True

        if litros > 0:
            disp = self.data["saldos"]["barril"][estilo]["disponible"]
            if disp < litros:
                puede = False
                razones.append(f"Barril {estilo}: necesita {litros}L, disponible {disp:.1f}L")

        if botellas > 0:
            disp = self.data["saldos"]["botella"][estilo]["disponible"]
            if disp < botellas:
                puede = False
                razones.append(f"Botella {estilo}: necesita {botellas} und, disponible {disp} und")

        # Verificar botellas vacías si se piden botellas
        if botellas > 0:
            vacias = self.insumos.get("botellas_vacias_limpias", {}).get("stock", 0)
            if vacias < botellas:
                puede = False
                razones.append(f"Botellas vacías: necesita {botellas}, stock {vacias}")

        return puede, "; ".join(razones) if razones else "OK"

    def get_alertas(self):
        return self.data.get("alertas", [])

    def get_cronograma(self):
        return self.data.get("cronograma", [])

    # ── Actualización masiva desde nucleo ──────────────────────────

    def actualizar_desde_nucleo(self, fermentadores, barriles, botellas_prod, fecha):
        anterior_ferm = {e: self.data["saldos"]["fermentador"][e]["litros"] for e in ESTILOS}
        anterior_barril = {e: self.data["saldos"]["barril"][e]["litros"] for e in ESTILOS}
        anterior_botella = {e: self.data["saldos"]["botella"][e]["unidades"] for e in ESTILOS}

        total_ferm_por_estilo = defaultdict(float)
        ferm_detalle = defaultdict(list)
        for key, data in fermentadores.items():
            estilo_raw = data.get("estilo", "")
            estilo = self._normalizar_estilo(estilo_raw)
            if estilo is None and estilo_raw:
                estilo = estilo_raw
            if estilo and estilo not in ESTILOS:
                ESTILOS.append(estilo)
            cap = FERM_CAPACIDADES.get(key, 400)
            litros = data.get("litros", 0)
            pct = litros / cap * 100 if cap else 0
            if estilo and estilo in ESTILOS:
                total_ferm_por_estilo[estilo] += litros
                ferm_detalle[estilo].append({
                    "nombre": FERM_NAMES.get(key, key),
                    "litros": litros,
                    "capacidad": cap,
                    "porcentaje": round(pct),
                })
            if key in self.data.setdefault("fermentadores", {}):
                self.data["fermentadores"][key] = {
                    "nombre": FERM_NAMES.get(key, key),
                    "estilo": estilo or "",
                    "litros": litros,
                    "capacidad": cap,
                    "porcentaje": round(pct),
                }

        for estilo in ESTILOS:
            actual = round(total_ferm_por_estilo.get(estilo, 0), 1)
            anterior = anterior_ferm[estilo]
            self.data["saldos"]["fermentador"][estilo]["litros"] = actual
            self.data["saldos"]["fermentador"][estilo]["fermentadores"] = ferm_detalle.get(estilo, [])
            pcts = [f["porcentaje"] for f in ferm_detalle.get(estilo, [])]
            self.data["saldos"]["fermentador"][estilo]["pct_max"] = max(pcts) if pcts else 0
            self.data["saldos"]["fermentador"][estilo]["alerta"] = (
                "roja" if actual == 0 else "verde"
            )

            delta = round(actual - anterior, 1)
            if abs(delta) > 0.5:
                self.registrar_entrada(
                    fecha, estilo, "fermentador_litros", actual,
                    f"nucleo_snapshot",
                    f"Anterior: {anterior}L → Actual: {actual}L (delta: {delta:+.1f}L)"
                )

        for estilo in ESTILOS:
            actual = round(barriles.get(estilo, 0), 1)
            anterior = anterior_barril.get(estilo, 0)
            delta = round(actual - anterior, 1)
            if delta > 0.5:
                self.data["saldos"]["barril"][estilo]["litros"] = round(
                    self.data["saldos"]["barril"][estilo]["litros"] + delta, 1)
                self._registrar_movimiento(
                    fecha, "ENTRADA", "nucleo_delta_barril", estilo, "barril_litros", delta,
                    f"Anterior: {anterior}L → Actual: {actual}L (delta: +{delta:.1f}L)"
                )
            elif delta < -0.5:
                self.data["saldos"]["barril"][estilo]["litros"] = max(0, round(
                    self.data["saldos"]["barril"][estilo]["litros"] + delta, 1))
                self._registrar_movimiento(
                    fecha, "SALIDA", "nucleo_delta_barril", estilo, "barril_litros", delta,
                    f"Anterior: {anterior}L → Actual: {actual}L (delta: {delta:+.1f}L)"
                )

        for estilo in ESTILOS:
            actual = int(botellas_prod.get(estilo, 0))
            anterior = anterior_botella.get(estilo, 0)
            delta = actual - anterior
            if delta > 0:
                self.data["saldos"]["botella"][estilo]["unidades"] += delta
                self._registrar_movimiento(
                    fecha, "ENTRADA", "nucleo_delta_botella", estilo, "botella_und", delta,
                    f"Anterior: {anterior} und → Actual: {actual} und (delta: +{delta})"
                )
            elif delta < 0:
                self.data["saldos"]["botella"][estilo]["unidades"] = max(0,
                    self.data["saldos"]["botella"][estilo]["unidades"] + delta)
                self._registrar_movimiento(
                    fecha, "SALIDA", "nucleo_delta_botella", estilo, "botella_und", delta,
                    f"Anterior: {anterior} und → Actual: {actual} und (delta: {delta})"
                )

        self._recalcular_disponibles()
        self._generar_alertas()
        self._guardar()

    def actualizar_desde_historial(self, historial):
        """Reconstruye el libro mayor desde la serie histórica (snapshots con forward-fill).

        - Genera movimientos unificados (ENTRADA/SALIDA) por deltas entre registros consecutivos.
        - Calcula el balance de masas por estilo y emite alerta DESBALANCE_MASAS (> 5 L).
        - Persiste snapshots[] para trazabilidad día a día.
        Es idempotente: puede re-ejecutarse con el histórico completo.
        """
        if not historial:
            return

        self.data["movimientos"] = []
        self.data["snapshots"] = []
        self._contador_mov = 1

        prev_ferm = {}
        prev_barril = {}
        prev_botella = {}
        desbalances = []
        ferm_tanques = {}

        for idx, snap in enumerate(historial):
            fecha = snap.get("fecha") or ""

            # ── Fermentadores: estado por tanque + agregado por estilo ──
            ferm_por_estilo = defaultdict(float)
            ferm_detalle = defaultdict(list)
            ferm_tanques = {}
            for key, fdata in snap.get("fermentadores", {}).items():
                estilo_raw = fdata.get("estilo", "")
                estilo = self._normalizar_estilo(estilo_raw)
                if estilo is None and estilo_raw:
                    estilo = estilo_raw
                litros = float(fdata.get("litros", 0) or 0)
                cap = FERM_CAPACIDADES.get(key, 400)
                ferm_tanques[key] = {
                    "nombre": FERM_NAMES.get(key, key),
                    "estilo": estilo or "",
                    "litros": round(litros, 1),
                    "capacidad": cap,
                    "porcentaje": round(litros / cap * 100) if cap else 0,
                }
                if estilo:
                    ferm_por_estilo[estilo] += litros
                    ferm_detalle[estilo].append({
                        "nombre": FERM_NAMES.get(key, key),
                        "litros": round(litros, 1),
                        "capacidad": cap,
                        "porcentaje": round(litros / cap * 100) if cap else 0,
                    })

            # ── Barriles y botellas por estilo ──
            barriles = {}
            for e, c in snap.get("barriles", {}).items():
                estilo = self._normalizar_estilo(e) or e
                barriles[estilo] = round(float(c), 1)
            botellas = {}
            for e, c in snap.get("botellas", {}).items():
                estilo = self._normalizar_estilo(e) or e
                botellas[estilo] = float(c)

            # ── Actualizar saldos corrientes (antes de movimientos: saldo_capa correcto) ──
            for estilo, lit in ferm_por_estilo.items():
                self.data["saldos"]["fermentador"].setdefault(
                    estilo, {"litros": 0, "fermentadores": [], "pct_max": 0, "alerta": "verde"})
                self.data["saldos"]["fermentador"][estilo]["litros"] = round(lit, 1)
                self.data["saldos"]["fermentador"][estilo]["fermentadores"] = ferm_detalle.get(estilo, [])
            for estilo, lit in barriles.items():
                self.data["saldos"]["barril"].setdefault(estilo, {"litros": 0, "comprometido": 0, "disponible": 0})
                self.data["saldos"]["barril"][estilo]["litros"] = lit
            for estilo, und in botellas.items():
                self.data["saldos"]["botella"].setdefault(estilo, {"unidades": 0, "comprometido": 0, "disponible": 0})
                self.data["saldos"]["botella"][estilo]["unidades"] = und

            # ── Primer registro = línea base (sin movimientos) ──
            if idx == 0:
                self.data["snapshots"].append({
                    "fecha": fecha,
                    "fermentadores": {k: dict(v) for k, v in ferm_tanques.items()},
                    "barriles": dict(barriles),
                    "botellas": dict(botellas),
                })
                prev_ferm = dict(ferm_por_estilo)
                prev_barril = dict(barriles)
                prev_botella = dict(botellas)
                continue

            # ── Deltas → movimientos + balance de masas ──
            estilos = set(ferm_por_estilo) | set(prev_ferm) | set(barriles) | set(prev_barril) | set(botellas) | set(prev_botella)
            for estilo in estilos:
                dF = round(ferm_por_estilo.get(estilo, 0.0) - prev_ferm.get(estilo, 0.0), 2)
                dB = round(barriles.get(estilo, 0.0) - prev_barril.get(estilo, 0.0), 2)
                dU = round(botellas.get(estilo, 0.0) - prev_botella.get(estilo, 0.0), 2)

                if dF != 0:
                    self._registrar_movimiento(
                        fecha, "ENTRADA" if dF > 0 else "SALIDA",
                        "produccion" if dF > 0 else "transferencia",
                        estilo, "fermentador_litros", dF,
                        f"Fermentador {estilo}: {prev_ferm.get(estilo, 0):.1f}L → {ferm_por_estilo.get(estilo, 0):.1f}L")
                if dB != 0:
                    self._registrar_movimiento(
                        fecha, "ENTRADA" if dB > 0 else "SALIDA",
                        "embarrilado" if dB > 0 else "venta",
                        estilo, "barril_litros", dB,
                        f"Barril {estilo}: {prev_barril.get(estilo, 0):.1f}L → {barriles.get(estilo, 0):.1f}L")
                if dU != 0:
                    self._registrar_movimiento(
                        fecha, "ENTRADA" if dU > 0 else "SALIDA",
                        "embotellado" if dU > 0 else "venta",
                        estilo, "botella_und", dU,
                        f"Botella {estilo}: {prev_botella.get(estilo, 0):.1f} und → {botellas.get(estilo, 0):.1f} und")

                entrada_barril = max(0.0, dB)
                entrada_botella = max(0.0, dU) * BOTELLA_L
                salida_upstream = max(0.0, -dF) + max(0.0, -dB)
                faltante = round(entrada_barril + entrada_botella - salida_upstream, 1)
                if faltante > UMBRAL_DESBALANCE and dF <= 0:
                    desbalances.append({
                        "tipo": "DESBALANCE_MASAS",
                        "urgencia": "alta",
                        "estilo": estilo,
                        "fecha": fecha,
                        "mensaje": (
                            f"{estilo}: entraron {entrada_barril:.1f}L a barril + "
                            f"{entrada_botella:.1f}L a botella = {entrada_barril + entrada_botella:.1f}L, "
                            f"pero aguas arriba solo salieron {salida_upstream:.1f}L "
                            f"(faltante {faltante:.1f}L). Revisar registro."
                        ),
                    })

            self.data["snapshots"].append({
                "fecha": fecha,
                "fermentadores": {k: dict(v) for k, v in ferm_tanques.items()},
                "barriles": dict(barriles),
                "botellas": dict(botellas),
            })

            prev_ferm = dict(ferm_por_estilo)
            prev_barril = dict(barriles)
            prev_botella = dict(botellas)

        # ── Estado final de tanques individuales ──
        self.data["fermentadores"] = ferm_tanques

        self._recalcular_disponibles()
        self._generar_alertas()
        self.data["alertas"] = desbalances + self.data.get("alertas", [])

        self._guardar()

    def _registrar_movimiento(self, fecha, tipo, origen, estilo, capa, cantidad, nota=""):
        """Registra un movimiento sin modificar saldos (ya modificados por el caller)."""
        mov = {
            "id": self._next_id(),
            "fecha": fecha,
            "tipo": tipo,
            "origen": origen,
            "estilo": estilo,
            "capa": capa,
            "cantidad": round(cantidad, 1),
            "nota": nota,
        }
        if capa == "barril_litros":
            mov["saldo_capa"] = self.data["saldos"]["barril"][estilo]["litros"]
        elif capa == "botella_und":
            mov["saldo_capa"] = self.data["saldos"]["botella"][estilo]["unidades"]
        elif capa == "fermentador_litros":
            mov["saldo_capa"] = self.data["saldos"]["fermentador"][estilo]["litros"]
        self.data["movimientos"].append(mov)

    # ── Cronograma ─────────────────────────────────────────────────

    def agregar_al_cronograma(self, fecha_estimada, estilo, capa_destino, litros, origen, responsable=""):
        self.data["cronograma"].append({
            "fecha_estimada": fecha_estimada,
            "estilo": estilo,
            "capa_origen": "fermentador",
            "origen": origen,
            "litros": litros,
            "capa_destino": capa_destino,
            "estado": "PLANIFICADO",
            "responsable": responsable or "Producción",
            "registrado": datetime.now().strftime("%Y-%m-%d"),
        })
        self._guardar()

    def actualizar_estado_cronograma(self, index, nuevo_estado, nota=""):
        if 0 <= index < len(self.data["cronograma"]):
            self.data["cronograma"][index]["estado"] = nuevo_estado
            if nota:
                self.data["cronograma"][index]["nota"] = nota
            self._guardar()

    # ── Insumos ────────────────────────────────────────────────────

    def actualizar_botellas_vacias(self, stock, proximo_pedido=None):
        self.insumos["botellas_vacias_limpias"]["stock"] = int(stock)
        self.insumos["botellas_vacias_limpias"]["estado"] = (
            "BAJO" if stock < 500 else
            "MEDIO" if stock < 1000 else "OK"
        )
        if proximo_pedido:
            self.insumos["botellas_vacias_limpias"]["proximo_pedido"] = proximo_pedido
        self._guardar_insumos()
        self._generar_alertas()
        self._guardar()

    def get_botellas_vacias(self):
        return self.insumos.get("botellas_vacias_limpias", {})

    # ── Internos ───────────────────────────────────────────────────

    def _capa_key(self, capa):
        if capa in ("barril", "barril_litros", "barril_litros"):
            return "barril"
        if capa in ("botella", "botella_und"):
            return "botella"
        return "fermentador"

    def _recalcular_disponibles(self):
        # Sincronizar fermentadores individuales → agregado por estilo
        por_estilo = defaultdict(lambda: {"litros": 0, "fermentadores": [], "pct_max": 0})
        for fkey, fdata in self.data.get("fermentadores", {}).items():
            estilo = fdata.get("estilo", "")
            if estilo and fdata["litros"] > 0:
                por_estilo[estilo]["litros"] = round(por_estilo[estilo]["litros"] + fdata["litros"], 1)
                por_estilo[estilo]["fermentadores"].append({
                    "nombre": fdata["nombre"],
                    "litros": fdata["litros"],
                    "capacidad": fdata["capacidad"],
                    "porcentaje": fdata["porcentaje"],
                })
                por_estilo[estilo]["pct_max"] = max(por_estilo[estilo]["pct_max"], fdata["porcentaje"])

        for estilo in ESTILOS:
            if estilo in por_estilo:
                self.data["saldos"]["fermentador"][estilo] = por_estilo[estilo]
                self.data["saldos"]["fermentador"][estilo]["alerta"] = "verde"
            elif estilo in self.data["saldos"]["fermentador"]:
                self.data["saldos"]["fermentador"][estilo] = {
                    "litros": 0, "fermentadores": [], "pct_max": 0, "alerta": "roja"
                }

        # Barril
        for estilo in ESTILOS:
            if estilo not in self.data["saldos"]["barril"]:
                self.data["saldos"]["barril"][estilo] = {"litros": 0, "comprometido": 0, "disponible": 0}
            b = self.data["saldos"]["barril"][estilo]
            b["disponible"] = max(0, round(b["litros"] - b.get("comprometido", 0), 1))

        # Botella
        for estilo in ESTILOS:
            if estilo not in self.data["saldos"]["botella"]:
                self.data["saldos"]["botella"][estilo] = {"unidades": 0, "comprometido": 0, "disponible": 0}
            bot = self.data["saldos"]["botella"][estilo]
            bot["disponible"] = max(0, bot["unidades"] - bot.get("comprometido", 0))

    def _generar_alertas(self):
        alertas = []

        # Botellas vacías
        vacias = self.insumos.get("botellas_vacias_limpias", {})
        stock_vacias = vacias.get("stock", 0)
        if stock_vacias < 500:
            alertas.append({
                "tipo": "BOTELLAS_VACIAS",
                "urgencia": "critica" if stock_vacias == 0 else "alta",
                "mensaje": f"Stock de botellas vacías limpias: {stock_vacias}. "
                           f"Se necesitan {1920 - stock_vacias} und (próximo pedido: {vacias.get('proximo_pedido', '??')})",
            })

        # Capa 1 → Capa 3: hay en fermentador pero no en botella
        for estilo in ESTILOS:
            ferm = self.data["saldos"]["fermentador"].get(estilo, {"litros": 0, "fermentadores": []})
            bot = self.data["saldos"]["botella"].get(estilo, {"unidades": 0, "comprometido": 0, "disponible": 0})
            if ferm["litros"] > 0 and bot.get("disponible", bot.get("unidades", 0)) < UMBRAL_BAJO_BOTELLA:
                alertas.append({
                    "tipo": "EMBOTELLAR_PENDIENTE",
                    "urgencia": "alta" if bot.get("disponible", 0) == 0 else "media",
                    "estilo": estilo,
                    "mensaje": f"{estilo}: {ferm['litros']:.0f}L en fermentador "
                               f"→ solo {bot.get('disponible', 0)} botellas disponibles. "
                               f"Se necesita embotellar.",
                    "fermentadores": [f["nombre"] for f in ferm.get("fermentadores", [])
                                      if f["porcentaje"] >= UMBRAL_FERMENTADOR_LISTO],
                })

        # Capa 1 → Capa 2: hay en fermentador pero no en barril
        for estilo in ESTILOS:
            ferm = self.data["saldos"]["fermentador"].get(estilo, {"litros": 0})
            barr = self.data["saldos"]["barril"].get(estilo, {"litros": 0, "comprometido": 0, "disponible": 0})
            if ferm["litros"] > 0 and barr.get("disponible", barr.get("litros", 0)) < UMBRAL_BAJO_BARRIL:
                alertas.append({
                    "tipo": "EMBARRILAR_PENDIENTE",
                    "urgencia": "alta" if barr.get("disponible", 0) == 0 else "media",
                    "estilo": estilo,
                    "mensaje": f"{estilo}: {ferm['litros']:.0f}L en fermentador "
                               f"→ solo {barr.get('disponible', 0):.1f}L en barril. "
                               f"Se necesita embarrilar.",
                })

        # 🔴 ALARMA DE PRODUCCIÓN: fermentador al ≤20% de capacidad
        for fkey, fdata in self.data.get("fermentadores", {}).items():
            if fdata["litros"] <= 0:
                continue
            estilo = fdata["estilo"]
            if not estilo:
                continue
            pct_ocupado = fdata["porcentaje"]
            pct_restante = 100 - pct_ocupado
            umbral_20 = fdata["capacidad"] * 0.20

            if fdata["litros"] <= umbral_20:
                barril_disp = self.data["saldos"]["barril"].get(estilo, {}).get("litros", 0)
                botella_disp = self.data["saldos"]["botella"].get(estilo, {}).get("unidades", 0)
                hay_stock_aguas_abajo = barril_disp > 0 or botella_disp > 0
                alertas.append({
                    "tipo": "PRODUCIR_ESTILO",
                    "urgencia": "critica" if not hay_stock_aguas_abajo else "alta",
                    "estilo": estilo,
                    "fermentador": fdata["nombre"],
                    "fermentador_key": fkey,
                    "mensaje": (
                        f"⏳ {fdata['nombre']} ({estilo}): solo {fdata['litros']:.0f}L restantes "
                        f"({pct_ocupado}% de {fdata['capacidad']}L). "
                        f"Barril: {barril_disp:.0f}L | Botella: {botella_disp:.0f} und. "
                        f"{'URGENTE: sin stock aguas abajo' if not hay_stock_aguas_abajo else 'Programar nueva cocción'}"
                    ),
                    "accion": f"PRODUCIR {estilo}",
                })

        # Compromisos pendientes de producción
        compromisos = [m for m in self.data["movimientos"]
                       if m["tipo"] == "COMPROMISO" and m.get("estado") == "PENDIENTE_PRODUCCION"]
        if compromisos:
            por_estilo = defaultdict(lambda: {"botella_und": 0, "barril_litros": 0, "clientes": []})
            for c in compromisos:
                por_estilo[c["estilo"]][c["capa"]] += abs(c["cantidad"])
                if c.get("cliente") and c["cliente"] not in por_estilo[c["estilo"]]["clientes"]:
                    por_estilo[c["estilo"]]["clientes"].append(c["cliente"])

            for estilo, data in por_estilo.items():
                partes = []
                if data["botella_und"] > 0:
                    partes.append(f"{data['botella_und']} botellas")
                if data["barril_litros"] > 0:
                    partes.append(f"{data['barril_litros']:.1f}L barril")
                alertas.append({
                    "tipo": "COMPROMISO_PENDIENTE",
                    "urgencia": "alta",
                    "estilo": estilo,
                    "mensaje": f"Pedidos comprometidos sin stock: {' + '.join(partes)} de {estilo} "
                               f"para {', '.join(data['clientes'][:3])}",
                })

        self.data["alertas"] = alertas

    def _normalizar_estilo(self, raw):
        if not raw:
            return None
        r = raw.strip().upper()
        if "STOUT" in r or "SANGRE NEGRA" in r or "PTL05" in r or "PTB05" in r:
            return "STOUT"
        if "AMERICAN INDIA PALE ALE" in r or "VAGABUNDO" in r or "PTL04" in r or "PTB04" in r:
            return "IPA"
        if "AMERICAN PALE ALE" in r or "CIENFUEGOS" in r or "PTL03" in r or "PTB03" in r:
            return "APA"
        if "IRISH RED ALE" in r or "MÍSTICA" in r or "MISTICA" in r or "PTL02" in r or "PTB02" in r:
            return "IRISH RED ALE"
        if "GOLDEN ALE" in r or "SIEMPRE VIVA" in r or "PTL01" in r or "PTB01" in r:
            return "GOLDEN ALE"
        if r in ("", "VACIO", "VACÍO"):
            return None
        if "RED IPA" in r or "RED INDIAN PALE ALE" in r:
            return "RED IPA"
        if "SCOTTISH" in r:
            return "SCOTTISH"
        if r in ESTILOS:
            return r
        return None


# ── CLI rápida ──────────────────────────────────────────────────────

def main():
    import sys
    ledger = LedgerInventario()

    if len(sys.argv) < 2:
        print("Uso: python ledger_inventario.py [resumen|alertas|disponible|cronograma|botellas_vacias|embarrilar|embotellar|vender]")
        print(f"  Ledger: {LEDGER_PATH}")
        print(f"  Insumos: {INSUMOS_PATH}")
        print()
        print("  embarrilar --fermentador F6 --litros 58.55 --estilo \"GOLDEN ALE\"")
        print("  embotellar  --origen barril --estilo \"GOLDEN ALE\" --botellas 170")
        print("  embotellar  --origen fermentador --fermentador F6 --estilo \"GOLDEN ALE\" --botellas 170")
        print("  vender      --capa barril --estilo \"GOLDEN ALE\" --cantidad 30")
        print("  vender      --capa botella --estilo \"IPA\" --cantidad 24")
        return

    cmd = sys.argv[1]

    if cmd == "resumen":
        print("\n=== FERMENTADORES ===")
        for fkey, fdata in ledger.data.get("fermentadores", {}).items():
            estilo = fdata.get("estilo", "—")
            print(f"  {fdata['nombre']:20s} | {estilo:20s} | {fdata['litros']:6.0f}L / {fdata['capacidad']:4d}L ({fdata['porcentaje']:2d}%)")
        print("\n=== SALDOS ===")
        for capa in ["barril", "botella"]:
            print(f"\n{capa.upper()}:")
            for e in ESTILOS:
                s = ledger.data["saldos"].get(capa, {}).get(e, {})
                if capa == "barril":
                    litros = s.get("litros", 0)
                    print(f"  {e:20s}: {litros:8.1f}L | comprometido: {s.get('comprometido', 0):6.1f}L | disponible: {s.get('disponible', 0):6.1f}L")
                else:
                    und = s.get("unidades", 0)
                    print(f"  {e:20s}: {und:5d} und | comprometido: {s.get('comprometido', 0):4d} und | disponible: {s.get('disponible', 0):4d} und")

    elif cmd == "alertas":
        print("\n=== ALERTAS ===")
        for a in ledger.get_alertas():
            urg = a["urgencia"].upper()
            icono = "🔴" if urg == "CRITICA" else "🟠" if urg == "ALTA" else "🟡"
            extra = ""
            if a.get("fermentador"):
                extra = f" [{a['fermentador']}]"
            if a.get("accion"):
                extra += f" → {a['accion']}"
            print(f"  {icono} [{a['tipo']}]{extra} {a['mensaje']}")

    elif cmd == "disponible":
        estilo = sys.argv[2] if len(sys.argv) > 2 else None
        if estilo:
            d = ledger.calcular_disponible(estilo=estilo)
            print(f"\n{estilo}:")
            print(f"  Barril: {d['barril_litros']:.1f}L")
            print(f"  Botella: {d['botella_und']} und")
        else:
            for e in ESTILOS:
                d = ledger.calcular_disponible(estilo=e)
                print(f"{e:20s} | Barril: {d['barril_litros']:6.1f}L | Botella: {d['botella_und']:5d} und")

    elif cmd == "cronograma":
        print("\n=== CRONOGRAMA DE PRODUCCIÓN ===")
        for i, c in enumerate(ledger.get_cronograma()):
            print(f"  [{i}] {c['fecha_estimada']} | {c['estilo']:20s} | {c['origen']} → {c['capa_destino']} | {c['litros']}L | {c['estado']}")

    elif cmd == "botellas_vacias":
        bv = ledger.get_botellas_vacias()
        print(f"\nBotellas vacías limpias: {bv['stock']} und ({bv['estado']})")
        print(f"  Pedido estándar: {bv['unidades_por_pedido']} und")
        print(f"  Próximo pedido: {bv.get('proximo_pedido', 'No programado')}")

    elif cmd == "embarrilar":
        args = _parsear_args(sys.argv[2:])
        fermentador = args.get("--fermentador") or args.get("-f")
        litros = float(args.get("--litros") or args.get("-l", 0))
        estilo = args.get("--estilo") or args.get("-e", "")
        nota = args.get("--nota", "")
        if not fermentador or litros <= 0:
            print("Uso: python ledger_inventario.py embarrilar --fermentador F6 --litros 58.55 [--estilo \"GOLDEN ALE\"]")
            return
        ok, msg = ledger.embarrilar(datetime.now().strftime("%Y-%m-%d"), fermentador, litros, nota)
        print(f"{'✅' if ok else '❌'} {msg}")

    elif cmd == "embotellar":
        args = _parsear_args(sys.argv[2:])
        origen = args.get("--origen", "barril")
        estilo = args.get("--estilo") or args.get("-e", "")
        botellas = int(args.get("--botellas") or args.get("-b", 0))
        fermentador = args.get("--fermentador") or args.get("-f")
        nota = args.get("--nota", "")
        if not estilo or botellas <= 0:
            print("Uso: python ledger_inventario.py embotellar --origen barril|fermentador --estilo \"IPA\" --botellas 170 [--fermentador F6]")
            return
        if origen == "fermentador" and not fermentador:
            print("❌ Para origen=fermentador debe especificar --fermentador")
            return
        ok, msg = ledger.embotellar(datetime.now().strftime("%Y-%m-%d"), estilo, botellas, origen, fermentador, nota)
        print(f"{'✅' if ok else '❌'} {msg}")

    elif cmd == "vender":
        args = _parsear_args(sys.argv[2:])
        capa = args.get("--capa", "botella")
        estilo = args.get("--estilo") or args.get("-e", "")
        cantidad = float(args.get("--cantidad") or args.get("-c", 0))
        cliente = args.get("--cliente", "")
        nota = args.get("--nota", "")
        if not estilo or cantidad <= 0:
            print("Uso: python ledger_inventario.py vender --capa barril|botella --estilo \"IPA\" --cantidad 30 [--cliente \"Nombre\"]")
            return
        if capa == "barril":
            ok, msg = ledger.vender_barril(datetime.now().strftime("%Y-%m-%d"), estilo, cantidad, cliente, nota)
        elif capa == "botella":
            ok, msg = ledger.vender_botella(datetime.now().strftime("%Y-%m-%d"), estilo, int(cantidad), cliente, nota)
        else:
            print(f"❌ Capa '{capa}' no válida. Use barril o botella.")
            return
        print(f"{'✅' if ok else '❌'} {msg}")


def _parsear_args(argv):
    args = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("--") or arg.startswith("-"):
            if i + 1 < len(argv) and not argv[i + 1].startswith("--") and not argv[i + 1].startswith("-"):
                args[arg] = argv[i + 1]
                i += 2
            else:
                args[arg] = True
                i += 1
        else:
            i += 1
    return args


if __name__ == "__main__":
    main()

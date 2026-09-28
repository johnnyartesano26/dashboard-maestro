# Changelog — Automatización Madre Monte

Registro de cambios relevantes en facturación, inventario y dashboards.

---

## 2026-09-28

### Corregido — Bug de "forward-fill" en la lectura de inventario
- **Causa:** el Sheet de inventario es un registro *incremental* (cada fila nueva solo trae las celdas que cambiaron). La facturación y el dashboard leían **solo la última fila**, por lo que desde el 22/09 veían el inventario casi vacío y marcaban las remisiones como "sin stock".
- **Solución:** se aplicó *forward-fill* (reproducir todo el historial en orden cronológico, conservando el último valor conocido; `0` = agotado; `VACIO` = tanque vacío), portando la lógica de `nucleo_de_inventario.py`.
- **Archivos:**
  - `crear-factura/facturacion_async.py` → `_leer_inventario` reescrito.
  - `crear-factura/sync_inventario.py` → `leer_inventario` reescrito.
  - `madremonte-dashboard/index.html` → pestaña Producción y gráfico histórico.

### Resultado
- Dry-run de facturación: `3 con stock suficiente | 0 sin stock | 0 errores`.
- Las 3 remisiones pendientes quedaron facturadas en Alegra (5081 SEVEN, 5083 PINEA, 5086 SAMUEL).
- Cola de facturación: `0` pendientes.

### Cambiado — Push por SSH en vez de HTTPS con token
- `dashboard-maestro/update_all_dashboards.sh` ahora pushea con `git@github.com:...` (SSH), eliminando la dependencia del `GITHUB_TOKEN` que estaba expirado (401).
- Ya no vuelve a fallar por expiración de token.

### Commits
| Repo | Commit |
|---|---|
| `madremonte-dashboard` | `470038b` — Forward-fill Producción + sync ledger |
| `crear-factura` | `c02340c` — Forward-fill facturación y sync |
| `dashboard-maestro` | `d550028` — Sync ledger |
| `dashboard-maestro` | `2b00efd` — Push por SSH |

### Pendiente (del README de automatización)
1. Alinear repo `dashboard-maestro` (divergido) y definir qué workflow es "dueño" de cada archivo.
2. Versionar en git el código de inventario (`nucleo_de_inventario.py`, `ledger_inventario.py`).
3. Archivar copias duplicadas de código de facturación.
4. Ampliar cobertura de pruebas (pytest) + Docker/CI.

# Mapa de Datos — Dashboards Madre Monte

## Bases de datos y su relación con cada dashboard

### 📊 1. Dashboard Maestro
**URL:** https://johnnyartesano26.github.io/dashboard-maestro/
**Repo:** https://github.com/johnnyartesano26/dashboard-maestro

| Fuente de datos | Archivo | Rango | Qué alimenta |
|---|---|---|---|
| Ventas Bar (CSV) | `data/ventas_mensuales.json` | Nov 2025 - Jun 2026 | KPIs, gráfica de ventas mensuales, summary cards |
| Ventas Bar (CSV) | `data/ventas_diarias.json` | Nov 2025 - Jun 2026 | Datos diarios (para futuras gráficas) |
| Facturación Alegra | `facturas_junio_2026.json` | Junio 2026 (900 facturas) | KPIs facturación, top 20 clientes, estado, tabla interactiva |
| Catálogo | `catalogo.json` | 8 meses configurados | Selector de periodos, metadatos, inventario básico |

---

### 📄 2. Facturación Junio 2026 (Interactivo)
**Archivo:** `Documents/Madre Monte/MadreMonte_Contexto/finanzas/facturas_junio_2026_interactivo.html`

| Fuente | Archivo | Qué alimenta |
|---|---|---|
| Facturación Alegra | `facturas_junio_2026.json` | Gráficas top 20, estado, diario, tabla buscador |

---

### 📄 3. Facturación Junio 2026 (Standalone)
**Archivo:** `Desktop/dashboard.html`

| Fuente | Qué alimenta |
|---|---|
| Datos embebidos en el HTML | Mismas gráficas pero sin depender de JSON externo |

---

### 🍺 4. Inventario — Semana 22-28 Junio 2026
**Archivo:** `Documents/Madre Monte/MadreMonte_Contexto/documentos/CEO/dashboard_inventario_22_junio_2026.html`

| Fuente | Qué alimenta |
|---|---|
| Datos embebidos en el HTML | 7 gráficas de fermentadores, botellas, barriles, materia prima |

---

### 🏦 5. Conciliaciones Bancarias
**URL:** https://johnnyartesano26.github.io/conciliaciones-bancarias/

| Fuente | Archivo | Qué alimenta |
|---|---|---|
| Checklist JSON | `data/checklist.json` | Tabla de comprobantes, KPIs, estado confirmado/no confirmado |
| Google Drive | `deepagente/Conciliaciones_Bancarias/` | Imágenes de comprobantes (OCR), extractos bancarios (CSV) |

---

## 📁 Fuentes de datos originales (carpetas locales)

| Categoría | Ubicación | Formato |
|---|---|---|
| **Ventas Bar diarias** | `.../Informe_bar_noviembre_junio_analisis/resumen_datos_diario.csv` | CSV (212 filas) |
| **Ventas Bar mensuales** | `.../Informe_bar_noviembre_junio_analisis/resumen_datos_mensual.csv` | CSV (8 filas) |
| **Facturación** | `.../finanzas/facturas_junio_2026.json` | JSON (900 facturas) |
| **Recibos de caja** | `.../finanzas/recibos_caja_junio_2026.json` | JSON (900 recibos) |
| **Inventario planta** | `.../inventario/registro_de_inventario/` | JSON + Excel |
| **Clientes Alegra** | `.../automatizaciones/clientes_backup_20260614.csv` | CSV (211 clientes) |

---

## 🔄 Flujo de actualización

```
CSV/Excel original → Script Python convierte a JSON → GitHub → GitHub Pages (dashboard)
                                                              → Google Drive (respaldo)
```

Para agregar un nuevo mes al Dashboard Maestro:
1. Agregar la fila al CSV `resumen_datos_mensual.csv`
2. Ejecutar script que regenera `ventas_mensuales.json`
3. Actualizar `catalogo.json` con los datos del nuevo mes
4. Push al repo → GitHub Pages se actualiza solo

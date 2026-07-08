# 🍺 Dashboard Maestro — Madre Monte

Dashboard unificado que integra facturación, inventario y resumen general de la cervecería Madre Monte.

## 🔗 Acceso

**Dashboard en vivo:** [johnnyartesano26.github.io/dashboard-maestro](https://johnnyartesano26.github.io/dashboard-maestro/)

## 📊 Pestañas

| Pestaña | Contenido |
|---|---|
| 📊 Resumen General | KPIs combinados, producción mensual, top 5 clientes, estado de facturas |
| 📄 Facturación | 900 facturas Junio 2026: top 20 clientes, estado, diario, tabla con buscador |
| 🍺 Inventario | 7 gráficas: fermentadores, ocupación, botellas, barriles, producción, comparativa, materia prima |

## 📂 Archivos

```
dashboard-maestro/
├── index.html                  # Dashboard principal
├── facturas_junio_2026.json   # Datos de 900 facturas (Alegra API)
└── dashboards.json            # Catálogo de todos los dashboards y sus rutas
```

## 🔧 Configuración de dashboards

El archivo `dashboards.json` contiene el catálogo completo de dashboards, rutas locales, URLs y fuentes de datos. Edítalo para mantener actualizados los enlaces cuando los dashboards evolucionen.

### Dashboards registrados

| ID | Nombre | Archivo local |
|---|---|---|
| `maestro` | Dashboard Maestro | `Desktop/dashboard-maestro/index.html` |
| `facturacion` | Facturación Junio 2026 (Interactivo) | `Documents/.../finanzas/facturas_junio_2026_interactivo.html` |
| `facturacion_standalone` | Facturación Junio 2026 (Standalone) | `Desktop/dashboard.html` |
| `inventario` | Inventario Semana 22-28 Junio | `Documents/.../CEO/dashboard_inventario_22_junio_2026.html` |

## 🚀 Desarrollo local

```bash
# Clonar
git clone git@github.com:johnnyartesano26/dashboard-maestro.git
cd dashboard-maestro

# Servir localmente
python3 -m http.server 8080
# Abrir http://localhost:8080
```

## 📡 Fuentes de datos

- **Facturación:** Alegra API v1 → `facturas_junio_2026.json`
- **Inventario:** Datos embebidos en el HTML (actualizar manualmente)

## 🛠 Stack

- HTML5 + CSS3 (tema oscuro GitHub-style)
- Chart.js v4.4.0
- Vanilla JavaScript (sin frameworks)
- GitHub Pages para deploy

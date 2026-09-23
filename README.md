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
- **Inventario:** `inventario_neto.json` + `ledger_inventario.json` (generados por el núcleo de inventario, ver sección de automatización)

## ⚠️ Problemas conocidos de automatización (22/09/2026)

### 1. `GITHUB_TOKEN` expirado
- El token en `~/.config/madremonte/.env` (prefijo `ghp_…`) fue rechazado por GitHub (`Invalid username or token`).
- **Impacto:** los pushes por HTTPS fallan. El cron de `madremonte-dashboard` (`update_all_dashboards.sh`, que sube `bar.html` vía `https://x-access-token:${GH_TOKEN}@…`) fallará hasta renovarlo.
- **Solución:** renovar el Personal Access Token y actualizarlo en `~/.config/madremonte/.env`. Alternativa: usar SSH (la llave `~/.ssh/id_ed25519` sí autentica).

### 2. Repo `dashboard-maestro` divergido (dos automatizaciones compitiendo)
- El clon local va **65 commits atrás y 6 adelante** de `origin/main`.
- **Causa:** dos sistemas escriben en el mismo repo con flujos distintos:
  - Cron local → commits `"Auto-inv: …"` (vía `update_inventario_neto.sh`).
  - GitHub Actions → commits `"Sync inventario: …"` / `"Diagnóstico facturación: …"` (workflows de `.github/workflows/`).
- **Impacto:** pushes no fast-forward y riesgo de conflictos en `data/inventario_neto.json`, `data/ledger_inventario.json`, `catalogo.json`, etc. **No reconciliar a ciegas.**
- **Pendiente:** alinear local con `origin` conservando los datos y definir qué workflow es "dueño" de cada archivo.

### 3. Código fuente del inventario no está en git
- `nucleo_de_inventario.py`, `ledger_inventario.py` y su `README.md` viven en `Documents/Madre Monte/MadreMonte_Contexto/inventario/registro_de_inventario/` (no es un repo git).
- **Impacto:** los cambios de lógica (forward-fill, deltas, alertas de desbalance) no están versionados ni respaldados en GitHub; solo existen en esta máquina.
- **Pendiente:** decidir si se versiona en un repo aparte o se mueve dentro de un repo existente.

### Nota sobre `ledger_inventario.json`
- Lo genera `ledger_inventario.py` y se sincroniza (`_sync_dashboard`) a `dashboard-maestro/data/` y `madremonte-dashboard/data/`.
- En `dashboard-maestro` **ningún HTML lo consume** (es espejo); su UI lee `inventario_neto.json`. Quien sí lo consume es `madremonte-dashboard` (pestaña "Historial").

## 🛠 Stack

- HTML5 + CSS3 (tema oscuro GitHub-style)
- Chart.js v4.4.0
- Vanilla JavaScript (sin frameworks)
- GitHub Pages para deploy

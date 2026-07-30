# Frontend (SvelteKit)

Web UI for the Water Security Tool. See the [root README](../README.md) and [docs/](../docs/)
for product overview, setup, and API details.

## Stack

- SvelteKit + Tailwind
- MapLibre GL (Diagnose 2D map)
- Plotly.js (Diagnose 3D DEM / layer drape)

## Develop

```sh
npm install
npm run dev
```

Opens on `http://localhost:5173`. `/api/*` is proxied to the FastAPI backend; `/titiler` via Vite.

## Modules

| Path | Module |
|------|--------|
| `src/lib/modules/diagnose/` | Map, 3D terrain, layers, zones, notes, hypotheses |
| `src/lib/modules/assess/` | ODK projects / forms / submissions |
| `src/lib/modules/design/` | Scaffold |
| `src/routes/(protected)/` | Authenticated Diagnose / Design / Assess pages |

## Build

```sh
npm run build
npm run preview
```

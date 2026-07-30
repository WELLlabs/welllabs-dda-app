# Setup

## Prerequisites

- Docker and Docker Compose
- Node.js 20+
- An AWS account with S3 access (COG layers, vector FlatGeobufs, watersheds, media)

## Project Structure

```
geo-field-pipeline/
├── backend/          FastAPI + PostGIS + GDAL
│   ├── app/
│   │   ├── main.py              App entry, router wiring
│   │   ├── shared/              Config, auth, DB, S3, access, ODK client
│   │   └── modules/
│   │       ├── accounts/        Auth, users, orgs, QField / ODK connectors
│   │       ├── diagnose/        Projects, layers, analysis, 3D drape, QField
│   │       │   └── config/      layers.yaml catalog
│   │       ├── design/          Boilerplate
│   │       └── assess/          ODK sync + forms/submissions
│   ├── db/init.sql              PostGIS schema
│   ├── scripts/                 run_tests.sh, prepare_secondary_layers.sh
│   ├── tests/                   Pytest suite
│   ├── docker-compose.yml       postgis + titiler + api
│   ├── Dockerfile
│   └── requirements.txt
├── docs/
└── frontend/         SvelteKit + Tailwind + MapLibre + Plotly
    └── src/
        ├── lib/modules/         Per-module API clients and components
        └── routes/(protected)/  Diagnose / Design / Assess pages
```

## Backend Setup

1. Copy the example environment file and fill in your values:

```bash
cd backend
cp .env.example .env
```

2. Configure environment variables in `.env` (see `.env.example` for the full list):

| Variable | Description |
|----------|-------------|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | S3 access |
| `AWS_S3_BUCKET` / `AWS_DEFAULT_REGION` | Bucket and region |
| `COG_LAYERS` | Comma-separated COG keys under `rasters/` |
| `VECTOR_LAYERS` | Comma-separated FlatGeobuf keys under `vector/` |
| `WATERSHEDS_FGB_KEY` | Watershed boundaries (`.fgb` or `.gpkg`) under `vector/` |
| `POSTGIS_PUBLIC_HOST` / `POSTGIS_PUBLIC_PORT` | Host QField can reach (not `localhost`) |
| `QFIELD_CLOUD_URL` / `QFIELD_PROJECT_NAME` | QField Cloud API + project name prefix |
| `QFIELD_RASTER_MIN_ZOOM` / `QFIELD_RASTER_MAX_ZOOM` | MBTiles zoom range for packages |
| `FRONTEND_ORIGIN` | CORS origin (default `http://localhost:5173`) |
| `SESSION_COOKIE_SECURE` | `true` in production (HTTPS) |
| `ODK_BASE_URL` / `ODK_USERNAME` / `ODK_PASSWORD` | Optional; Assess ODK sync |
| `metabase_embed_secret_key` / `metabase_dashboard_id` | Optional settings fields for a future Metabase embed (not in `.env.example` yet) |

3. Start all services:

```bash
docker compose up -d
```

Containers:
- **postgis** — PostGIS 16, schema from `db/init.sql`
- **titiler** — COG tile server
- **api** — FastAPI on port 8080 (volume-mounts `./app` for hot reload)

4. Verify:

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

> **Note:** If `main.py` imports a missing Assess Metabase router, the API process may fail to start until that module exists or the import is removed. Diagnose and Assess ODK routes are otherwise independent.

## Backend tests

```bash
cd backend
bash scripts/run_tests.sh
```

Runs pytest inside the API image with `tests/` mounted. Most suite coverage is unit-level
(accounts, diagnose catalog/helpers, access). App smoke tests need a loadable `app.main`.

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Dev server: `http://localhost:5173`. `/api/*` is proxied to FastAPI; `/titiler` via Vite proxy.

## S3 Bucket Layout

```
your-bucket/
├── rasters/*.tif                    Shared COG rasters (LULC, DEM, JRC, …)
├── vector/*.fgb|*.gpkg              Secondary vectors + watershed boundaries
├── {project_id}/media/{file}        Field note photos/audio
└── {project_id}/packages/{...}      QField package artifacts
```

IAM: `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on `arn:aws:s3:::your-bucket/*`.

Layer styling is not stored in S3 — edit `backend/app/modules/diagnose/config/layers.yaml`.

## Database Reset

```bash
cd backend
docker compose down -v
docker compose up -d
```

`-v` drops the PostgreSQL volume so `init.sql` runs again.

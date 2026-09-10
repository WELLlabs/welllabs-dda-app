# DevOps — production deploy on EC2

CodeDeploy + CodePipeline deliver this repo to EC2 (`ai.welllabs.org`). Nginx terminates
TLS from Cloudflare; systemd runs FastAPI and SvelteKit.

## Layout

```
devops/
├── buildspec.yml              # CodeBuild: package artifact + deploy-env ARN pointer
├── nginx/welllabs.conf        # Reverse proxy (paths below)
├── systemd/
│   ├── welllabs-backend.service   # uvicorn :8080
│   └── welllabs-frontend.service  # adapter-node :3000
├── scripts/
│   ├── before_install.sh      # apt deps, free ports, Docker
│   ├── after_install.sh       # Secrets Manager → .env, venv, frontend build, nginx, QGIS image
│   ├── application_start.sh   # Restart backend / frontend / nginx
│   └── validate_service.sh    # /health JSON check (with :8080 fallback)
└── cloudflare/                # Worker 1101 notes + passthrough script
    └── README.md
```

Root `appspec.yml` wires the four hooks. Pipeline name (dev):
`well-labs-dda-product-dev-pipeline` (ap-south-1). Push to `dev` triggers deploy to
**https://beta.welllabs.org/wst** (prod is `main` → **https://ai.welllabs.org/wst**).

## Production URL map

| Browser path | Upstream |
|--------------|----------|
| `/wst/` | SvelteKit (`kit.paths.base = /wst`) on `:3000` |
| `/wst/backend/*` | FastAPI internal `/api/*` on `:8080` |
| `/wst/api/*`, `/api/*` | **301** → `/wst/backend/*` |
| `/diagnose/*`, `/assess/*`, … | **301** → `/wst/...` (bookmarks without base path) |
| `/health` | FastAPI `{"status":"ok"}` (CodeDeploy ValidateService) |

**Always use `/wst/backend/` for browser API calls** — not `/wst/api/`. A Cloudflare Worker
on this host crashes **POST** to `/wst/api/*` (error 1101). Details:
[cloudflare/README.md](cloudflare/README.md).

Google OAuth redirect URIs (register both in Google Cloud Console):

```
https://beta.welllabs.org/wst/backend/accounts/auth/google/callback   # dev secret
https://ai.welllabs.org/wst/backend/accounts/auth/google/callback     # prod secret
```

Env on the host (from Secrets Manager + defaults in `after_install.sh`):

| Key | Role |
|-----|------|
| `FRONTEND_BASE_PATH` | `/wst` — drives `api_public_prefix` → `/wst/backend` |
| `FRONTEND_ORIGIN` / `ORIGIN` | CORS + SvelteKit adapter origin |
| `PACKAGES_DIR` / `HOST_PACKAGES_DIR` | QField package workspace under `/opt/welllabs/shared/packages` |
| `DATABASE_URL` | PostGIS (passwords with `&` / `%` / `@` are OK for the app; GDAL uses `PGPASSWORD`) |

## Deploy hooks (what runs on EC2)

1. **BeforeInstall** — free `:8080` / `:3000`; install `jq`, Python 3.12 venv, **GDAL**,
   `postgresql-client`, nginx, **Node 22+**, **`docker.io`** (enable + start Docker).
2. **AfterInstall** — fetch app secret → `/opt/welllabs/shared/.env`; create release under
   `/opt/welllabs/releases/<timestamp>`; backend venv + `pip install`; frontend `npm ci` +
   `npm run build`; install nginx/systemd units; **pre-pull** `qgis/qgis:release-3_34`;
   symlink `/opt/welllabs/current`.
3. **ApplicationStart** — restart `welllabs-backend`, `welllabs-frontend`, nginx.
4. **ValidateService** — curl `/health` (or `127.0.0.1:8080/health`) until JSON `"ok"`;
   soft-check `GET /wst/`.

Only one CodeDeploy deployment can run at a time — wait for success/failure before
pushing again.

## QField packaging on production

Diagnose **Package to QField** needs:

| Dependency | Why |
|------------|-----|
| **GDAL / gdal-bin** (Ubuntu ≈ 3.4) | `ogr2ogr` (vectors), `gdalwarp` (COG → watershed GeoTIFF). Do **not** pass `-cutline_srs` (unsupported on this GDAL). |
| **Docker** + image `qgis/qgis:release-3_34` | PyQGIS builds the `.qgs` project. Without Docker the SSE stream fails after “Generating QGIS project…”. |
| **`DATABASE_URL` via `PGPASSWORD`** | ogr2ogr must not embed URL-encoded passwords in the `PG:` DSN. |
| Writable `PACKAGES_DIR` | Per-project package trees under shared packages. |

Local `docker compose` mounts the Docker socket into the API container for the same
PyQGIS step. On EC2 the backend runs under systemd and calls host `docker` directly.

## Smoke checks after deploy

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://ai.welllabs.org/wst/
curl -sS https://ai.welllabs.org/wst/backend/assess/status
# POST should return JSON (e.g. 422), not Cloudflare 1101
curl -sS -o /dev/null -w "%{http_code}\n" -X POST \
  https://ai.welllabs.org/wst/backend/accounts/auth/login \
  -H 'Content-Type: application/json' -d '{"email":"x","password":"y"}'
```

## Related docs

- [../README.md](../README.md) — product overview + local quick start
- [../docs/setup.md](../docs/setup.md) — local env and Docker Compose
- [../docs/auth.md](../docs/auth.md) — OAuth callback URLs
- [cloudflare/README.md](cloudflare/README.md) — Worker 1101 remediation

#!/bin/bash
set -e

echo ""
echo "============================================================"
echo " AfterInstall started : $(date)"
echo "============================================================"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RELEASE_DIR="/opt/welllabs/releases/$TIMESTAMP"
SHARED_DIR="/opt/welllabs/shared"
SHARED_ENV="${SHARED_DIR}/.env"
PACKAGES_DIR="${SHARED_DIR}/packages"

# Derive the deployment archive root from this script's own location:
# Script is at <archive>/devops/scripts/after_install.sh  →  go up 2 levels.
DEPLOY_ARCHIVE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Normalize all deployment scripts to Unix (LF) line endings (safety for Windows checkouts)
find "${DEPLOY_ARCHIVE}/devops/scripts" -type f -name "*.sh" -exec sed -i 's/\r$//' {} +

# ──────────────────────────────────────────────────────────────────────────────
# [1/7] Read deploy-env from build artifact  →  gets the secret ARN
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- [1/7] Reading deploy-env from artifact ---"

[[ -f "${DEPLOY_ARCHIVE}/deploy-env" ]] || {
  echo "ERROR: deploy-env not found in ${DEPLOY_ARCHIVE}."
  echo "Check: buildspec.yml post_build step writes this file."
  exit 1
}

# Strip leading whitespace (heredoc indentation written by buildspec cat <<EOF)
sed -i 's/^[[:space:]]*//' "${DEPLOY_ARCHIVE}/deploy-env"

source "${DEPLOY_ARCHIVE}/deploy-env"

for var in PROJECT_NAME APP_CONFIG_SECRET_ARN; do
  [[ -n "${!var:-}" ]] || {
    echo "ERROR: '${var}' is missing or empty in deploy-env."
    echo "Check: Terraform pipeline module injects APP_CONFIG_SECRET_ARN and PROJECT_NAME."
    exit 1
  }
done

echo "Project        : ${PROJECT_NAME}"
echo "App Config ARN : ${APP_CONFIG_SECRET_ARN}"

# ──────────────────────────────────────────────────────────────────────────────
# [2/7] Fetch the app-config secret from Secrets Manager
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- [2/7] Fetching secret from AWS Secrets Manager ---"

APP_CONFIG_JSON=$(aws secretsmanager get-secret-value \
  --secret-id "${APP_CONFIG_SECRET_ARN}" \
  --query SecretString \
  --output text 2>&1) || {
  echo "ERROR: Failed to fetch secret '${APP_CONFIG_SECRET_ARN}'."
  echo "Check: EC2 IAM role has secretsmanager:GetSecretValue on this ARN."
  echo "Run:   aws sts get-caller-identity   (to confirm role is attached)"
  exit 1
}

# ──────────────────────────────────────────────────────────────────────────────
# [3/7] Validate JSON
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- [3/7] Validating secret JSON ---"

jq -e . > /dev/null 2>&1 <<< "${APP_CONFIG_JSON}" || {
  echo "ERROR: Secret value is not valid JSON."
  echo "Check: Add secret values as JSON in AWS Console → Secrets Manager."
  exit 1
}

echo "Keys in secret : $(jq -r 'keys | join(", ")' <<< "${APP_CONFIG_JSON}")"

# ──────────────────────────────────────────────────────────────────────────────
# [4/7] Validate critical required fields (FastAPI / PostGIS)
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- [4/7] Validating required fields ---"

# Keys read by app.shared.config.Settings (pydantic-settings) + Node ORIGIN
REQUIRED_FIELDS=(
  "DATABASE_URL"
  "AUTH_JWT_SECRET"
  "FRONTEND_ORIGIN"
  "AWS_S3_BUCKET"
  "AWS_DEFAULT_REGION"
)

for field in "${REQUIRED_FIELDS[@]}"; do
  VALUE=$(jq -r ".${field} // empty" <<< "${APP_CONFIG_JSON}")
  [[ -n "${VALUE}" ]] || {
    echo "ERROR: Required field '${field}' is missing or empty in Secrets Manager."
    echo "Fix:   AWS Console → Secrets Manager → ${APP_CONFIG_SECRET_ARN} → Edit secret value"
    echo "       Add key: ${field}"
    echo "See backend/.env.example for the full FastAPI env schema."
    exit 1
  }
  echo "  ✓ ${field} is present"
done

# ──────────────────────────────────────────────────────────────────────────────
# [5/7] Write /opt/welllabs/shared/.env  (all keys from JSON, dynamically)
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- [5/7] Writing ${SHARED_ENV} ---"

mkdir -p "${SHARED_DIR}" "${PACKAGES_DIR}"

# Generate .env for systemd EnvironmentFile + pydantic-settings.
# Always double-quote values (spaces/special chars). Do not bash-`source`
# this file later — pull DATABASE_URL with jq instead.
export APP_CONFIG_JSON
python3 - "${SHARED_ENV}" "${PACKAGES_DIR}" <<'PY'
import json, os, re, sys
from pathlib import Path
from urllib.parse import urlparse

shared_env = Path(sys.argv[1])
packages_dir = sys.argv[2]
cfg = json.loads(os.environ["APP_CONFIG_JSON"])

def escape(value: object) -> str:
    s = "" if value is None else str(value)
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("$", "\\$")
        .replace("`", "\\`")
    )

# Normalize FRONTEND_ORIGIN to host-only for CORS / adapter-node ORIGIN
raw_origin = str(cfg.get("FRONTEND_ORIGIN") or "").strip()
u = urlparse(raw_origin)
frontend_origin_host = (
    f"{u.scheme}://{u.netloc}" if u.scheme and u.netloc else raw_origin.rstrip("/")
)
if frontend_origin_host:
    cfg["FRONTEND_ORIGIN"] = frontend_origin_host

defaults = {
    "ORIGIN": frontend_origin_host,
    "FRONTEND_BASE_PATH": "/wst",
    "API_URL": "http://127.0.0.1:8080",
    "API_PUBLIC_URL": "http://127.0.0.1:8080",
    "SESSION_COOKIE_SECURE": "true",
    "HOST_PACKAGES_DIR": packages_dir,
    "PACKAGES_DIR": packages_dir,
}
for key, value in defaults.items():
    cfg.setdefault(key, value)

lines = [f'{key}="{escape(value)}"' for key, value in cfg.items()]
shared_env.write_text("\n".join(lines) + "\n", encoding="utf-8")

# Expose host for later steps in this shell via a tiny sidecar file
Path(str(shared_env) + ".frontend_origin_host").write_text(
    frontend_origin_host + "\n", encoding="utf-8"
)
PY

FRONTEND_ORIGIN_HOST=$(tr -d '\r\n' < "${SHARED_ENV}.frontend_origin_host")
FRONTEND_HOST=$(echo "${FRONTEND_ORIGIN_HOST}" | sed -E 's#^https?://##; s#/.*$##')
rm -f "${SHARED_ENV}.frontend_origin_host"
# Secure: only root can read it
chmod 600 "${SHARED_ENV}"
chown root:root "${SHARED_ENV}"

echo ".env written  : ${SHARED_ENV}"
echo "─────────────────────────────────────────────────────────────"
# Log keys — mask values that look sensitive
while IFS='=' read -r key value; do
  if [[ "$key" =~ (SECRET|PASSWORD|TOKEN|KEY|AWS_SECRET|DATABASE_URL) ]]; then
    echo "  $key=[REDACTED, ${#value} chars]"
  else
    echo "  $key=$value"
  fi
done < "${SHARED_ENV}"
echo "─────────────────────────────────────────────────────────────"

# ──────────────────────────────────────────────────────────────────────────────
# [6/7] Build the new release
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- [6/7] Creating release $TIMESTAMP ---"
mkdir -p "$RELEASE_DIR"
cp -r "$DEPLOY_ARCHIVE/." "$RELEASE_DIR/"

# Symlink the shared .env into the release backend directory
ln -sf "${SHARED_ENV}" "${RELEASE_DIR}/backend/.env"
echo "  .env symlinked → ${RELEASE_DIR}/backend/.env"

# Shared packages volume for QField builds
mkdir -p "${RELEASE_DIR}/backend/packages"
ln -sfn "${PACKAGES_DIR}" "${RELEASE_DIR}/backend/packages/shared" 2>/dev/null || true

# ──────────────────────────────────────────────────────────────────────────────
# Backend: Python virtual environment (FastAPI / uvicorn)
# ──────────────────────────────────────────────────────────────────────────────
echo "Setting up Python virtual environment..."
cd "$RELEASE_DIR/backend"

PYTHON_BIN=$(command -v python3.12 || command -v python3.11 || command -v python3 || true)
if [ -z "$PYTHON_BIN" ]; then
  echo "ERROR: No Python 3 interpreter found on this instance."
  exit 1
fi
echo "Using Python: $PYTHON_BIN ($($PYTHON_BIN --version))"

"$PYTHON_BIN" -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate

echo "Installing Python dependencies..."
pip install --upgrade pip -q

# GDAL pip package must match the system libgdal version when present
if command -v gdal-config >/dev/null 2>&1; then
  GDAL_SYS_VERSION=$(gdal-config --version)
  echo "Installing GDAL==$GDAL_SYS_VERSION (matching system library)..."
  pip install "GDAL==$GDAL_SYS_VERSION" -q || echo "WARNING: GDAL pip install failed; continuing with requirements.txt"
fi

# Install remaining requirements (skip an explicit GDAL pin to avoid version conflict)
if grep -iq "^gdal" requirements.txt; then
  grep -iv "^gdal" requirements.txt | pip install -r /dev/stdin -q
else
  pip install -r requirements.txt -q
fi

# ──────────────────────────────────────────────────────────────────────────────
# Database: ensure PostGIS schema (idempotent init + migrations)
# ──────────────────────────────────────────────────────────────────────────────
echo "Applying PostGIS schema / migrations..."
DATABASE_URL=$(jq -r '.DATABASE_URL // empty' <<< "${APP_CONFIG_JSON}")
if [ -z "${DATABASE_URL}" ]; then
  echo "ERROR: DATABASE_URL empty in Secrets Manager JSON"
  exit 1
fi
export DATABASE_URL

PSQL=(psql "${DATABASE_URL}" -v ON_ERROR_STOP=1)

"${PSQL[@]}" -c "CREATE EXTENSION IF NOT EXISTS postgis;" >/dev/null

USERS_EXISTS=$("${PSQL[@]}" -tAc "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='users'" | tr -d '[:space:]')
if [ "$USERS_EXISTS" != "1" ]; then
  echo "Fresh database — applying db/init.sql"
  "${PSQL[@]}" -f "$RELEASE_DIR/backend/db/init.sql"
else
  echo "Existing schema detected (users table present) — skipping init.sql"
fi

if [ -d "$RELEASE_DIR/backend/db/migrations" ]; then
  echo "Applying db/migrations/*.sql (idempotent)..."
  for migration in "$RELEASE_DIR/backend/db/migrations/"*.sql; do
    [ -f "$migration" ] || continue
    echo "  → $(basename "$migration")"
    "${PSQL[@]}" -f "$migration"
  done
fi

deactivate

# ──────────────────────────────────────────────────────────────────────────────
# Frontend: Node.js / SvelteKit build (adapter-node, base=/wst)
# ──────────────────────────────────────────────────────────────────────────────
echo "Building SvelteKit frontend..."
cd "$RELEASE_DIR/frontend"

export PATH="/usr/local/bin:/usr/bin:$PATH"

NPM_BIN=$(command -v npm || true)
if [ -z "$NPM_BIN" ]; then
  echo "ERROR: npm not found. Ensure before_install.sh ran successfully."
  exit 1
fi
echo "Using npm: $NPM_BIN ($(npm --version)), Node: $(node --version)"

# Public origin for any build-time absolute URLs
export ORIGIN="${FRONTEND_ORIGIN_HOST}"
export PUBLIC_ORIGIN="${FRONTEND_ORIGIN_HOST}"
export API_URL="http://127.0.0.1:8080"

# DevDependencies are required to *build* SvelteKit (vite, adapter-node, etc.)
# --ignore-engines: EC2 may briefly lag package engine pins during Node upgrades
npm ci --os=linux --cpu=x64 --ignore-engines || npm install --os=linux --cpu=x64 --ignore-engines
npm run build

# ──────────────────────────────────────────────────────────────────────────────
# Nginx & systemd configs
# ──────────────────────────────────────────────────────────────────────────────
echo "Installing Nginx & systemd configs..."

# ── TLS certificate for port 443 ─────────────────────────────────────────────
# Cloudflare connects to origin on port 443 (SSL mode = Full / Full Strict).
# We need nginx to listen on 443; generate a long-lived self-signed cert if one
# doesn't already exist.  Cloudflare "Full" mode accepts self-signed certs.
# cp "$RELEASE_DIR/devops/nginx/welllabs.conf" /etc/nginx/conf.d/welllabs.conf
mkdir -p /etc/ssl/welllabs
if [ ! -f /etc/ssl/welllabs/cert.pem ] || [ ! -f /etc/ssl/welllabs/key.pem ]; then
  echo "Generating self-signed TLS certificate for origin port 443..."
  openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout /etc/ssl/welllabs/key.pem \
    -out    /etc/ssl/welllabs/cert.pem \
    -subj "/CN=${FRONTEND_HOST}"
  if [ ! -f /etc/ssl/welllabs/cert.pem ]; then
    echo "ERROR: openssl failed to generate certificate — aborting"
    exit 1
  fi
  chmod 600 /etc/ssl/welllabs/key.pem
  echo "  ✓ Certificate written to /etc/ssl/welllabs/"
else
  echo "  ✓ Existing TLS certificate found — skipping generation."
fi

# ── Nginx nginx.conf skeleton (always rewritten — eliminates stale server blocks)
# nginx.conf is a clean skeleton that ONLY includes welllabs.conf.
# The welllabs.conf site config is PRESERVED across deploys (see below).

# Remove stale conf.d fragments and sites-enabled symlinks (but NOT welllabs.conf)
find /etc/nginx/conf.d/ -name '*.conf' ! -name 'welllabs.conf' -delete 2>/dev/null || true
rm -f /etc/nginx/sites-enabled/*

# Rewrite nginx.conf to a clean skeleton
cat > /etc/nginx/nginx.conf << 'NGINX_MAIN'
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {
    worker_connections 1024;
    multi_accept on;
}

http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    server_tokens off;

    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    access_log /var/log/nginx/access.log;
    error_log  /var/log/nginx/error.log;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript
               text/xml application/xml application/xml+rss text/javascript;

    # Single application config — the only server block we run.
    include /etc/nginx/conf.d/welllabs.conf;
}
NGINX_MAIN

# ── Nginx site config: PRESERVE across re-deploys ─────────────────────────────
# Strategy:
#   • First deploy (no welllabs.conf): install from template, patch LE cert.
#   • Re-deploys: keep the existing config — it already has the correct cert
#     paths (Let's Encrypt or self-signed) from the first deploy or manual fix.
#     Only reload nginx to pick up new app code. No overwriting.
#
# Result: SSL cert config survives every pipeline run automatically.

NGINX_CONF=/etc/nginx/conf.d/welllabs.conf

if [ -f "${NGINX_CONF}" ] && nginx -t 2>/dev/null; then
  echo "  ✓ Existing nginx config is valid — preserving it (not overwriting on redeploy)."
else
  echo "  ℹ Installing nginx site config from template (first deploy or broken config)."
  cp "$RELEASE_DIR/devops/nginx/welllabs.conf" "${NGINX_CONF}"

  # Apply Let's Encrypt cert if available (preferred over self-signed)
  LE_CERT="/etc/letsencrypt/live/${FRONTEND_HOST}/fullchain.pem"
  LE_KEY="/etc/letsencrypt/live/${FRONTEND_HOST}/privkey.pem"
  if [ -f "${LE_CERT}" ] && [ -f "${LE_KEY}" ]; then
    echo "  ✓ Let's Encrypt cert found for ${FRONTEND_HOST} — patching nginx config."
    sed -i "s|ssl_certificate[[:space:]][^;]*;|ssl_certificate ${LE_CERT};|" "${NGINX_CONF}"
    sed -i "s|ssl_certificate_key[[:space:]][^;]*;|ssl_certificate_key ${LE_KEY};|" "${NGINX_CONF}"
  else
    echo "  ℹ No Let's Encrypt cert — using self-signed (Cloudflare SSL must be Full, not Full Strict)."
  fi
fi

if ! nginx -t; then
  echo "ERROR: Nginx config test failed — aborting."
  exit 1
fi
echo "  ✓ Nginx config OK."

# Start/reload nginx
systemctl enable nginx
if systemctl is-active --quiet nginx; then
  systemctl reload nginx || systemctl restart nginx
else
  systemctl start nginx
fi
echo "  ✓ Nginx is running."

cp "$RELEASE_DIR/devops/systemd/welllabs-backend.service"  /etc/systemd/system/
cp "$RELEASE_DIR/devops/systemd/welllabs-frontend.service" /etc/systemd/system/
systemctl daemon-reload

# Pre-pull PyQGIS image so first QField package does not block on a multi-GB download.
if command -v docker >/dev/null 2>&1; then
  echo "Pre-pulling QGIS Docker image for QField packaging..."
  docker pull qgis/qgis:release-3_34 || echo "WARN: QGIS image pull failed — retry on next deploy or first package"
else
  echo "WARN: docker not available — QField PyQGIS packaging will fail until Docker is installed"
fi

# ──────────────────────────────────────────────────────────────────────────────
# [7/7] Atomic symlink swap to new release
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- [7/7] Swapping symlink to new release: $TIMESTAMP ---"
ln -sfn "$RELEASE_DIR" /opt/welllabs/current

# Cleanup: keep only last 3 releases
echo "Cleaning up old releases..."
cd /opt/welllabs/releases
ls -dt */ | tail -n +4 | xargs rm -rf 2>/dev/null || echo "Warning: cleanup had issues, continuing..."

echo ""
echo "============================================================"
echo " AfterInstall DONE : $(date)"
echo " Release : $TIMESTAMP"
echo "============================================================"
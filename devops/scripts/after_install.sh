#!/bin/bash
set -e
echo "=== AfterInstall: Building new release ==="

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RELEASE_DIR="/opt/welllabs/releases/$TIMESTAMP"

# Derive the deployment archive root from this script's own location:
# Script is at <archive>/devops/scripts/after_install.sh  →  go up 2 levels.
DEPLOY_ARCHIVE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# ──────────────────────────────────────
# 1. Copy source to new release directory
# ──────────────────────────────────────
echo "[1/7] Creating release $TIMESTAMP (archive: $DEPLOY_ARCHIVE)..."
mkdir -p "$RELEASE_DIR"
cp -r "$DEPLOY_ARCHIVE/." "$RELEASE_DIR/"

# ──────────────────────────────────────
# 2. Link shared .env file
# ──────────────────────────────────────
echo "[2/7] Linking shared .env..."
ln -sf /opt/welllabs/shared/.env "$RELEASE_DIR/backend/.env"

# ──────────────────────────────────────
# 3. Backend: Python virtual environment
# ──────────────────────────────────────
echo "[3/7] Setting up Python virtual environment..."
cd "$RELEASE_DIR/backend"

# Detect the best available Python 3 binary
PYTHON_BIN=$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3 || true)
if [ -z "$PYTHON_BIN" ]; then
  echo "ERROR: No Python 3 interpreter found on this instance."
  exit 1
fi
echo "Using Python: $PYTHON_BIN ($($PYTHON_BIN --version))"

"$PYTHON_BIN" -m venv venv
source venv/bin/activate

echo "[4/7] Installing Python dependencies..."
pip install --upgrade pip -q

# GDAL pip package must match the system libgdal version exactly
GDAL_SYS_VERSION=$(gdal-config --version)
echo "Installing GDAL==$GDAL_SYS_VERSION (matching system library)..."
pip install GDAL==$GDAL_SYS_VERSION -q

# Install remaining requirements (skip the GDAL line to avoid version conflict)
grep -iv "^gdal" requirements.txt | pip install -r /dev/stdin -q

# ──────────────────────────────────────
# 4. Database setup & Django migrations
# ──────────────────────────────────────
echo "[5/7] Checking database..."
if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw ddaapp; then
    echo "Database 'ddaapp' does not exist. Creating it now..."
    sudo -u postgres psql -c "CREATE DATABASE ddaapp;"
    sudo -u postgres psql -d ddaapp -c "CREATE EXTENSION postgis;"

    # Pull DB password from .env instead of hardcoding it
    DB_PASS=$(grep ^DB_PASSWORD /opt/welllabs/shared/.env | cut -d= -f2)
    sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD '$DB_PASS';"
fi

echo "Running Django migrations & collectstatic..."
python manage.py makemigrations --noinput
python manage.py migrate --noinput
python manage.py collectstatic --noinput

deactivate

# ──────────────────────────────────────
# 5. Frontend: Node.js build
# ──────────────────────────────────────
echo "[6/7] Building SvelteKit frontend..."
cd "$RELEASE_DIR/frontend"

export PATH="/usr/local/bin:/usr/bin:$PATH"

NPM_BIN=$(command -v npm || true)
if [ -z "$NPM_BIN" ]; then
  echo "ERROR: npm not found. Ensure before_install.sh ran successfully."
  exit 1
fi
echo "Using npm: $NPM_BIN ($(npm --version)), Node: $(node --version)"

# Use npm install (not npm ci) to handle cross-platform lockfile differences.
# The lockfile may be missing linux-x64 rollup binaries if generated on macOS/Windows.
npm install --os=linux --cpu=x64
npm run build

# ──────────────────────────────────────
# 6. Nginx & systemd configs
# ──────────────────────────────────────
echo "[7/7] Installing Nginx & systemd configs..."

# Back up existing nginx config in case the new one is invalid
cp /etc/nginx/conf.d/welllabs.conf /etc/nginx/conf.d/welllabs.conf.bak 2>/dev/null || true

# Install new config
cp "$RELEASE_DIR/devops/nginx/welllabs.conf" /etc/nginx/conf.d/welllabs.conf
rm -f /etc/nginx/conf.d/default.conf
rm -f /etc/nginx/sites-enabled/default


# Validate using the real nginx.conf (which includes conf.d/) — NOT -c on the file directly
# because conf.d files contain server{} blocks which are only valid inside http{} context.
if ! nginx -t; then
    echo "ERROR: Nginx config invalid — restoring previous config..."
    mv /etc/nginx/conf.d/welllabs.conf.bak /etc/nginx/conf.d/welllabs.conf
    exit 1
fi
rm -f /etc/nginx/conf.d/welllabs.conf.bak

# Systemd service units
cp "$RELEASE_DIR/devops/systemd/welllabs-backend.service" /etc/systemd/system/
cp "$RELEASE_DIR/devops/systemd/welllabs-frontend.service" /etc/systemd/system/
systemctl daemon-reload

# ──────────────────────────────────────
# 7. Symlink swap — atomic
# ──────────────────────────────────────
echo ">>> Swapping symlink to new release: $TIMESTAMP"
ln -sfn "$RELEASE_DIR" /opt/welllabs/current

# ──────────────────────────────────────
# Cleanup: keep only last 3 releases
# ──────────────────────────────────────
echo "Cleaning up old releases..."
cd /opt/welllabs/releases
ls -dt */ | tail -n +4 | xargs rm -rf 2>/dev/null || echo "Warning: cleanup had issues, continuing..."

echo "=== Release $TIMESTAMP ready ==="
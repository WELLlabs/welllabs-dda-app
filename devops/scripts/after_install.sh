#!/bin/bash
set -e
echo "=== AfterInstall: Building new release ==="

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RELEASE_DIR="/opt/welllabs/releases/$TIMESTAMP"
DEPLOY_SRC="/tmp/welllabs-deploy"

# ──────────────────────────────────────
# 1. Copy source to new release directory
# ──────────────────────────────────────
echo "[1/7] Creating release $TIMESTAMP..."
cp -r "$DEPLOY_SRC" "$RELEASE_DIR"

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
python3 -m venv venv
source venv/bin/activate

echo "[4/7] Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# ──────────────────────────────────────
# 4. Django migrations & static files
# ──────────────────────────────────────
echo "[5/7] Running Django migrations & collectstatic..."
python manage.py migrate --noinput
python manage.py collectstatic --noinput

deactivate

# ──────────────────────────────────────
# 5. Frontend: Node.js build
# ──────────────────────────────────────
echo "[6/7] Building SvelteKit frontend..."
cd "$RELEASE_DIR/frontend"
npm ci
npm run build

# ──────────────────────────────────────
# 6. Copy Nginx & systemd configs
# ──────────────────────────────────────
echo "[7/7] Installing Nginx & systemd configs..."

# Nginx config
cp "$RELEASE_DIR/devops/nginx/welllabs.conf" /etc/nginx/conf.d/welllabs.conf
rm -f /etc/nginx/conf.d/default.conf
nginx -t  # Validate config before proceeding

# Systemd service units
cp "$RELEASE_DIR/devops/systemd/welllabs-backend.service" /etc/systemd/system/
cp "$RELEASE_DIR/devops/systemd/welllabs-frontend.service" /etc/systemd/system/
systemctl daemon-reload

# ──────────────────────────────────────
# 7. SYMLINK SWAP — instant, atomic
# ──────────────────────────────────────
echo ">>> Swapping symlink to new release: $TIMESTAMP"
ln -sfn "$RELEASE_DIR" /opt/welllabs/current

# ──────────────────────────────────────
# Cleanup: keep only last 3 releases
# ──────────────────────────────────────
echo "Cleaning up old releases..."
cd /opt/welllabs/releases
ls -dt */ | tail -n +4 | xargs rm -rf || true

echo "=== Release $TIMESTAMP ready ==="

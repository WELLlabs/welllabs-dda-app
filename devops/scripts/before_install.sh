#!/bin/bash
set -e
echo "=== BeforeInstall: Preparing for deployment ==="

# Create necessary directories if they don't exist
mkdir -p /opt/welllabs/{releases,shared,logs,shared/packages}

# ── Free ports before deployment ──────────────────────────────────────────────
# Kill anything occupying the app service ports.
# Port 8080 — FastAPI (uvicorn).  Old service must vacate so uvicorn binds.
# Port 3000 — SvelteKit (node).   Same reason.
# Do NOT kill 80/443 here — nginx must keep serving traffic during the deploy.
# Ports 80/443 are cleared in application_start.sh immediately before nginx starts.
echo "Freeing ports 8080 and 3000..."
fuser -k 8080/tcp 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
# Brief pause to let the OS release the sockets cleanly before we start new services
sleep 2

# Stop unattended-upgrades temporarily to avoid dpkg lock conflicts
echo "Stopping unattended-upgrades if active..."
systemctl stop unattended-upgrades || true

# Wait for unattended-upgrades or apt processes to finish
echo "Waiting for existing apt/dpkg locks to release..."
for i in {1..20}; do
  if ! pgrep -f "unattended-upgrades" >/dev/null && ! pgrep -f "apt-get" >/dev/null && ! pgrep -f "dpkg" >/dev/null; then
    break
  fi
  echo "Lock process active. Waiting 5 seconds (attempt $i/20)..."
  sleep 5
done

# Configure any half-installed packages to fix interrupted dpkg errors
echo "Configuring any interrupted packages..."
DEBIAN_FRONTEND=noninteractive dpkg --configure -a || true

# Run apt-get update and install with retries
echo "Installing system dependencies..."
apt_retry() {
  local count=0
  until "$@"; do
    if [ $count -gt 5 ]; then
      echo "ERROR: Failed to run command: $*"
      exit 1
    fi
    echo "Apt lock held or network issue. Retrying in 5 seconds (retry $((count++)))..."
    sleep 5
  done
}

apt_retry apt-get update -y
# jq — Secrets Manager JSON
# python3.12-venv — FastAPI venv
# libgdal / gdal-bin — diagnose packaging / geospatial
# postgresql-client — schema migrations via psql
# nginx — reverse proxy (reload in ApplicationStart)
apt_retry apt-get install -y \
  jq \
  python3.12-venv \
  libgdal-dev \
  gdal-bin \
  curl \
  openssl \
  postgresql-client \
  nginx \
  docker.io

# Docker — PyQGIS QField project builder (qgis/qgis container)
systemctl enable docker || true
systemctl start docker || true

# Install / upgrade Node.js 22+ (SvelteKit / jsdom transitive deps require >=22.13)
NODE_MAJOR=0
if command -v node &>/dev/null; then
  NODE_MAJOR=$(node -v | sed 's/^v\([0-9]*\).*/\1/')
  echo "Node.js already installed: $(node --version) (major=${NODE_MAJOR})"
fi
if [ "${NODE_MAJOR}" -lt 22 ]; then
  echo "Installing Node.js 22.x (required for frontend build)..."
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt_retry apt-get install -y nodejs
  echo "Node.js now: $(node --version), npm: $(npm --version)"
fi

# /opt/welllabs/shared/.env is written by after_install.sh via AWS Secrets Manager.
echo "Shared .env will be written from Secrets Manager during AfterInstall."

# Detect deployment archive location dynamically
DEPLOY_ARCHIVE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [ -f "$DEPLOY_ARCHIVE/allowed_hosts.txt" ]; then
  EC2_IP=$(cat "$DEPLOY_ARCHIVE/allowed_hosts.txt" | tr -d '\r' | xargs || echo "")
  if [ -n "$EC2_IP" ]; then
    echo "ALLOWED_HOSTS / public host hint from pipeline: $EC2_IP"
  else
    echo "allowed_hosts.txt exists but value is empty"
  fi
else
  echo "allowed_hosts.txt not found — skipping"
fi

echo "=== Ready for new release ==="

# Free disk before AfterInstall builds a new venv (beta has failed with ENOSPC).
echo "--- Disk before prune ---"
df -h / /tmp /opt 2>/dev/null || df -h /
echo "Pruning old Well Labs releases (keep current + 1 previous)..."
if [ -d /opt/welllabs/releases ]; then
  CURRENT_TARGET=""
  if [ -L /opt/welllabs/current ]; then
    CURRENT_TARGET=$(readlink -f /opt/welllabs/current || true)
  fi
  # shellcheck disable=SC2012
  mapfile -t RELEASE_DIRS < <(ls -1dt /opt/welllabs/releases/*/ 2>/dev/null || true)
  kept=0
  for dir in "${RELEASE_DIRS[@]}"; do
    abs=$(readlink -f "$dir" || true)
    # Always keep the live symlink target.
    if [ -n "$CURRENT_TARGET" ] && [ "$abs" = "$CURRENT_TARGET" ]; then
      echo "  keep (current): $dir"
      kept=$((kept + 1))
      continue
    fi
    # Keep one additional recent release for rollback.
    if [ "$kept" -lt 2 ]; then
      echo "  keep: $dir"
      kept=$((kept + 1))
      continue
    fi
    echo "  remove: $dir"
    rm -rf "$dir"
  done
fi
echo "Clearing package caches and stale deploy scratch..."
rm -rf /tmp/welllabs-deploy 2>/dev/null || true
rm -rf /root/.cache/pip /home/*/.cache/pip 2>/dev/null || true
rm -rf /root/.npm/_cacache /home/*/.npm/_cacache 2>/dev/null || true
journalctl --vacuum-size=200M >/dev/null 2>&1 || true
# Do not docker prune -a: keeps qgis/qgis image needed for QField packaging.
docker builder prune -f >/dev/null 2>&1 || true
echo "--- Disk after prune ---"
df -h / /tmp /opt 2>/dev/null || df -h /

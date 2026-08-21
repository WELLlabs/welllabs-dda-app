#!/bin/bash
set -e
echo "=== BeforeInstall: Preparing for deployment ==="

# Create necessary directories if they don't exist
mkdir -p /opt/welllabs/{releases,shared,logs,shared/packages}

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
  postgresql-client \
  nginx

# Install Node.js 20 (includes npm) only if not already present
if ! command -v node &>/dev/null; then
  echo "Node.js not found, installing..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt_retry apt-get install -y nodejs
else
  echo "Node.js already installed: $(node --version)"
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

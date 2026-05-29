#!/bin/bash
set -e
echo "=== BeforeInstall: Preparing for deployment ==="

# Create necessary directories if they don't exist
mkdir -p /opt/welllabs/{releases,shared,logs}

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

# Run apt-get update and install with retries
echo "Installing system dependencies..."
apt_retry() {
  local count=0
  until "$@"; do
    if [ $count -gt 5 ]; then
      echo "ERROR: Failed to run command: $@"
      exit 1
    fi
    echo "Apt lock held or network issue. Retrying in 5 seconds (retry $((count++)))..."
    sleep 5
  done
}

apt_retry apt-get update -y
apt_retry apt-get install -y jq python3.12-venv libgdal-dev gdal-bin curl

# Install Node.js 20 (includes npm) only if not already present
if ! command -v node &>/dev/null; then
  echo "Node.js not found, installing..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
else
  echo "Node.js already installed: $(node --version)"
fi

# Verify that the shared .env file exists and contains valid config (restores defaults if corrupted/empty)
if [ ! -f /opt/welllabs/shared/.env ] || ! grep -q "^SECRET_KEY=" /opt/welllabs/shared/.env; then
  echo "Warning: /opt/welllabs/shared/.env is missing or invalid (possibly corrupted by a previous run). Restoring defaults..."
  cat > /opt/welllabs/shared/.env << 'ENVFILE'
DB_NAME=ddaapp
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
DEBUG=False
SECRET_KEY=change-me-to-a-secure-key
ALLOWED_HOSTS=localhost,127.0.0.1
ENVFILE
  chmod 600 /opt/welllabs/shared/.env
else
  echo "/opt/welllabs/shared/.env verified successfully. Preserving host configurations."
fi

# Detect deployment archive location dynamically
DEPLOY_ARCHIVE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Apply ALLOWED_HOSTS dynamically from pipeline if passed
if [ -f "$DEPLOY_ARCHIVE/allowed_hosts.txt" ]; then
  EC2_IP=$(cat "$DEPLOY_ARCHIVE/allowed_hosts.txt" | tr -d '\r' | xargs || echo "")
  if [ -n "$EC2_IP" ]; then
    echo "Updating ALLOWED_HOSTS in /opt/welllabs/shared/.env with value from Pipeline: $EC2_IP"
    if grep -q "^ALLOWED_HOSTS=" /opt/welllabs/shared/.env; then
      sed -i "s|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=localhost,127.0.0.1,$EC2_IP|" /opt/welllabs/shared/.env
    else
      echo "ALLOWED_HOSTS=localhost,127.0.0.1,$EC2_IP" >> /opt/welllabs/shared/.env
    fi
  else
    echo "allowed_hosts.txt exists but value is empty"
  fi
else
  echo "allowed_hosts.txt not found — skipping dynamic ALLOWED_HOSTS update"
fi

echo "=== Ready for new release ==="
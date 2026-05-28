#!/bin/bash
set -e
echo "=== BeforeInstall: Preparing for deployment ==="

# Create necessary directories if they don't exist
mkdir -p /opt/welllabs/{releases,shared,logs}

# Install system dependencies
apt-get update -y
apt-get install -y jq python3.12-venv libgdal-dev gdal-bin curl 

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
ALLOWED_HOSTS=localhost,127.0.0.1,*
ENVFILE
  chmod 600 /opt/welllabs/shared/.env
else
  echo "/opt/welllabs/shared/.env verified successfully. Preserving host configurations."
fi

# Apply ALLOWED_HOSTS dynamically from pipeline if passed
if [ -f allowed_hosts.txt ]; then
  PIPELINE_HOSTS=$(cat allowed_hosts.txt | tr -d '\r' | xargs || echo "")
  if [ -n "$PIPELINE_HOSTS" ]; then
    echo "Updating ALLOWED_HOSTS in /opt/welllabs/shared/.env with value from Pipeline: $PIPELINE_HOSTS"
    sed -i "s|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=localhost,127.0.0.1,$PIPELINE_HOSTS|" /opt/welllabs/shared/.env
  fi
fi

echo "=== Ready for new release ==="
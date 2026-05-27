#!/bin/bash
set -e
echo "=== BeforeInstall: Preparing for deployment ==="

# ── AWS Secrets Manager secret ARN ─────────────────────────────────────────
SECRET_ARN="arn:aws:secretsmanager:ap-south-1:590183894970:secret:well_labs_dda-Ojzru9"
REGION="ap-south-1"
# ───────────────────────────────────────────────────────────────────────────

# Create app directories if they don't exist (first deployment)
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

# Fetch secret from AWS Secrets Manager and write it as .env
echo "Fetching secrets from AWS Secrets Manager..."
aws secretsmanager get-secret-value \
  --secret-id "$SECRET_ARN" \
  --region "$REGION" \
  --query SecretString \
  --output text \
  | jq -r 'to_entries[] | "\(.key)=\(.value)"' \
  > /opt/welllabs/shared/.env

chmod 600 /opt/welllabs/shared/.env
echo ".env written from Secrets Manager successfully."

echo "=== Ready for new release ==="
#!/bin/bash
set -e
echo "=== BeforeInstall: Preparing for deployment ==="

# Create app directories if they don't exist (first deployment)
mkdir -p /opt/welllabs/{releases,shared,logs}

echo "=== Ready for new release ==="

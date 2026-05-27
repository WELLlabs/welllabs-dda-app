#!/bin/bash
set -e
echo "=== ValidateService: Running health check ==="

# Wait for services to fully start
sleep 8

# Check backend health endpoint via Nginx
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health/)

if [ "$HTTP_CODE" -eq 200 ]; then
    echo "✓ Health check passed (HTTP $HTTP_CODE)"
    echo ""
    echo "Service Status:"
    echo "  Backend:  $(systemctl is-active welllabs-backend.service)"
    echo "  Frontend: $(systemctl is-active welllabs-frontend.service)"
    echo "  Nginx:    $(systemctl is-active nginx)"
    echo ""
    echo "=== Deployment successful! ==="
    exit 0
else
    echo "✗ Health check FAILED (HTTP $HTTP_CODE)"
    echo ""
    echo "Service Status:"
    echo "  Backend:  $(systemctl is-active welllabs-backend.service)"
    echo "  Frontend: $(systemctl is-active welllabs-frontend.service)"
    echo "  Nginx:    $(systemctl is-active nginx)"
    echo ""
    echo "Backend logs:"
    journalctl -u welllabs-backend.service --no-pager -n 20 || true
    echo ""
    echo "=== Deployment FAILED — CodeDeploy will rollback ==="
    exit 1
fi

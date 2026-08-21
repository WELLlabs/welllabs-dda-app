#!/bin/bash
set -e
echo "=== ValidateService: Running health check ==="

# ──────────────────────────────────────
# Retry loop — up to 30s (10 × 3s)
# Hit FastAPI /health through nginx
# ──────────────────────────────────────
MAX_RETRIES=10
RETRY_INTERVAL=3
HTTP_CODE=000

for i in $(seq 1 $MAX_RETRIES); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health || echo "000")
    echo "  Attempt $i/$MAX_RETRIES → GET /health → HTTP $HTTP_CODE"

    if [ "$HTTP_CODE" -eq 200 ]; then
        break
    fi

    if [ "$i" -lt "$MAX_RETRIES" ]; then
        sleep $RETRY_INTERVAL
    fi
done

# ──────────────────────────────────────
# Helper: print service status block
# ──────────────────────────────────────
print_status() {
    echo ""
    echo "Service Status:"
    echo "  Backend:  $(systemctl is-active welllabs-backend.service)"
    echo "  Frontend: $(systemctl is-active welllabs-frontend.service)"
    echo "  Nginx:    $(systemctl is-active nginx)"
    echo ""
}

# ──────────────────────────────────────
# Evaluate result
# ──────────────────────────────────────
if [ "$HTTP_CODE" -eq 200 ]; then
    # Soft-check frontend path (non-fatal — health already proves API + nginx)
    FRONT_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/wst/ || echo "000")
    echo "  Soft check GET /wst/ → HTTP $FRONT_CODE"

    echo "✓ Health check passed (HTTP $HTTP_CODE)"
    print_status
    echo "=== Deployment successful! ==="
    exit 0
else
    echo "✗ Health check FAILED after $MAX_RETRIES attempts (last HTTP code: $HTTP_CODE)"

    if [ "$HTTP_CODE" = "000" ]; then
        echo "  → Connection refused: Nginx may be down or not yet listening."
    elif [ "$HTTP_CODE" -eq 502 ] || [ "$HTTP_CODE" -eq 503 ]; then
        echo "  → Nginx is up but FastAPI is not responding (upstream error)."
    elif [ "$HTTP_CODE" -eq 404 ]; then
        echo "  → Nginx is up but /health not found — check devops/nginx/welllabs.conf."
    fi

    print_status

    echo "Backend logs:"
    journalctl -u welllabs-backend.service --no-pager -n 30 || true
    echo ""
    echo "Frontend logs:"
    journalctl -u welllabs-frontend.service --no-pager -n 20 || true
    echo ""
    echo "Nginx logs:"
    journalctl -u nginx --no-pager -n 10 || true
    echo ""
    echo "=== Deployment FAILED — CodeDeploy will rollback ==="
    exit 1
fi

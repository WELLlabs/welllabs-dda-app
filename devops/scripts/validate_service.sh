#!/bin/bash
set -e
echo "=== ValidateService: Running health check ==="

# ──────────────────────────────────────
# Retry loop — up to 30s (10 × 3s)
# Hit FastAPI /health through nginx
# ──────────────────────────────────────
MAX_RETRIES=12
RETRY_INTERVAL=2
HTTP_CODE=000
HEALTH_BODY=""

for i in $(seq 1 $MAX_RETRIES); do
    RESPONSE=$(curl -s -w $'\n%{http_code}' --max-time 5 http://localhost/health 2>/dev/null || printf '\n000')
    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    HEALTH_BODY=$(echo "$RESPONSE" | sed '$d')
    echo "  Attempt $i/$MAX_RETRIES → GET /health → HTTP $HTTP_CODE body=${HEALTH_BODY}"

    # Verify FastAPI is actually running: it returns JSON {"status":"ok"}.
    # An old SvelteKit service on port 8080 would return HTML and pass a naive
    # HTTP-200 check, but our app would be broken. Require the JSON sentinel.
    if [ "$HTTP_CODE" -eq 200 ] && echo "$HEALTH_BODY" | grep -q '"ok"'; then
        break
    fi

    HTTP_CODE=000  # reset so the success check below fails unless we broke out early
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
if [ "$HTTP_CODE" -eq 200 ] && echo "$HEALTH_BODY" | grep -q '"ok"'; then
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

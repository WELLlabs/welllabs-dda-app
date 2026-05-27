#!/bin/bash
set -e
echo "=== ApplicationStart: Zero-downtime reload ==="

# ──────────────────────────────────────
# Backend: Gunicorn (graceful reload if running)
# ──────────────────────────────────────
if systemctl is-active --quiet welllabs-backend.service; then
    echo "→ Gunicorn is running — sending graceful reload (SIGHUP)..."
    echo "  Old workers will finish current requests, then new workers start."
    systemctl kill -s HUP welllabs-backend.service
else
    echo "→ Gunicorn not running — starting fresh..."
    if ! systemctl is-enabled --quiet welllabs-backend.service; then
        systemctl enable welllabs-backend.service
    fi
    systemctl start welllabs-backend.service
fi

# Verify backend came up
sleep 5
if ! systemctl is-active --quiet welllabs-backend.service; then
    echo "ERROR: Backend failed to start. Journal logs:"
    journalctl -u welllabs-backend.service --no-pager -n 50
    exit 1
fi
echo "  ✓ Backend is active."

# ──────────────────────────────────────
# Frontend: Node.js (restart — no hot reload support)
# ──────────────────────────────────────
echo "→ Restarting SvelteKit frontend..."
if ! systemctl is-enabled --quiet welllabs-frontend.service; then
    systemctl enable welllabs-frontend.service
fi
systemctl restart welllabs-frontend.service

# Verify frontend came up
sleep 3
if ! systemctl is-active --quiet welllabs-frontend.service; then
    echo "ERROR: Frontend failed to start. Journal logs:"
    journalctl -u welllabs-frontend.service --no-pager -n 50
    exit 1
fi
echo "  ✓ Frontend is active."
 
# ──────────────────────────────────────
# Nginx: Reload config (zero downtime)
# ──────────────────────────────────────
echo "→ Reloading Nginx configuration..."
nginx -t && systemctl reload nginx
echo "  ✓ Nginx reloaded."

echo ""
echo "=== All services running ==="
echo "  Backend  → http://127.0.0.1:8000 (Gunicorn/Django)"
echo "  Frontend → http://127.0.0.1:3000 (Node/SvelteKit)"
echo "  Nginx    → http://0.0.0.0:80     (Reverse Proxy)"
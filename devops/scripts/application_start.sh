#!/bin/bash
set -e
echo "=== ApplicationStart: Zero-downtime reload ==="

# ──────────────────────────────────────
# Backend: Uvicorn / FastAPI
# ──────────────────────────────────────
echo "→ Restarting FastAPI backend (uvicorn)..."
if ! systemctl is-enabled --quiet welllabs-backend.service; then
    systemctl enable welllabs-backend.service
fi
systemctl restart welllabs-backend.service

# Verify backend came up
sleep 5
if ! systemctl is-active --quiet welllabs-backend.service; then
    echo "ERROR: Backend failed to start. Journal logs:"
    journalctl -u welllabs-backend.service --no-pager -n 50
    exit 1
fi
echo "  ✓ Backend is active."

# ──────────────────────────────────────
# Frontend: Node.js / SvelteKit
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
# Nginx: Reload config
# ──────────────────────────────────────
echo "→ Reloading Nginx configuration..."
# Stop nginx cleanly before evicting stale listeners on 80/443.
systemctl stop nginx 2>/dev/null || true
# A legacy service (e.g. old SvelteKit on port 443 with Restart=always) may
# have rebound to port 443 during the deployment.  Kill it one final time so
# nginx can bind both port 80 and 443.
fuser -k 80/tcp  2>/dev/null || true
fuser -k 443/tcp 2>/dev/null || true
sleep 2
if ! nginx -t; then
    echo "ERROR: Nginx config invalid:"
    nginx -t 2>&1 || true
    exit 1
fi
systemctl enable nginx
systemctl start nginx
if ! systemctl is-active --quiet nginx; then
    echo "ERROR: Nginx failed to start. Journal logs:"
    journalctl -u nginx --no-pager -n 30
    exit 1
fi
echo "  ✓ Nginx started."

echo ""
echo "=== All services running ==="
echo "  Backend  → http://127.0.0.1:8080 (Uvicorn / FastAPI)"
echo "  Frontend → http://127.0.0.1:3000 (Node / SvelteKit, base=/wst)"
echo "  Nginx    → http://0.0.0.0:80     (Reverse Proxy)"
echo "  App URL  → /wst/   API → /api/   Health → /health"

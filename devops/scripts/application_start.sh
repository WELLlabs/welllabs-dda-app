#!/bin/bash
set -e
echo "=== ApplicationStart: Zero-downtime reload ==="

ensure_nginx() {
    echo "→ Ensuring Nginx is running with latest config..."
    if ! nginx -t; then
        echo "ERROR: Nginx config invalid:"
        nginx -t 2>&1 || true
        return 1
    fi
    systemctl enable nginx
    if systemctl is-active --quiet nginx; then
        # Prefer reload — keeps port 80/443 bound (avoids 521 during deploy).
        systemctl reload nginx && echo "  ✓ Nginx reloaded." && return 0
        echo "  Reload failed — restarting nginx..."
        systemctl stop nginx 2>/dev/null || true
    fi
    # Not running (or reload failed): evict stale listeners then start.
    fuser -k 80/tcp  2>/dev/null || true
    fuser -k 443/tcp 2>/dev/null || true
    sleep 2
    systemctl start nginx
    if ! systemctl is-active --quiet nginx; then
        echo "ERROR: Nginx failed to start. Journal logs:"
        journalctl -u nginx --no-pager -n 30
        return 1
    fi
    echo "  ✓ Nginx started."
}

# Nginx first so origin stays reachable even if app services restart slowly.
ensure_nginx

# ──────────────────────────────────────
# Backend: Uvicorn / FastAPI
# ──────────────────────────────────────
echo "→ Restarting FastAPI backend (uvicorn)..."
if ! systemctl is-enabled --quiet welllabs-backend.service; then
    systemctl enable welllabs-backend.service
fi
systemctl restart welllabs-backend.service

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

sleep 3
if ! systemctl is-active --quiet welllabs-frontend.service; then
    echo "ERROR: Frontend failed to start. Journal logs:"
    journalctl -u welllabs-frontend.service --no-pager -n 50
    exit 1
fi
echo "  ✓ Frontend is active."

# Re-check nginx after service restarts (legacy processes can grab 443).
ensure_nginx

echo ""
echo "=== All services running ==="
echo "  Backend  → http://127.0.0.1:8080 (Uvicorn / FastAPI)"
echo "  Frontend → http://127.0.0.1:3000 (Node / SvelteKit, base=/wst)"
echo "  Nginx    → http://0.0.0.0:80 / https://0.0.0.0:443 (Reverse Proxy)"
echo "  App URL  → /wst/   API → /api/   Health → /health"

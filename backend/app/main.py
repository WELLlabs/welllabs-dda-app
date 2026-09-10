from contextlib import asynccontextmanager

import html
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.modules.accounts.routers import auth, orgs, qfield_account, users
from app.modules.assess.routers import access as assess_access
from app.modules.assess.routers import assess, mel, mel_projects, reports as assess_reports
from app.modules.design.routers import design
from app.modules.diagnose.routers import (
    field_notes,
    hypotheses,
    layers,
    observation_zones,
    qfield,
    diagnosis,
    watersheds,
)
from app.shared.config import settings
from app.shared.database import close_pool, init_pool
from app.shared.oauth_redirect import request_public_app_base
from app.shared.forwarded_host import ForwardedHostMiddleware
from app.shared.users.db import engine as users_async_engine

# Metabase router is optional until Assess ships the module.
try:
    from app.modules.assess.routers import metabase as metabase_router
except ImportError:  # pragma: no cover
    metabase_router = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Keep the pool small — each uvicorn worker creates its own pool.
    # min_size=0: do not block process start on Postgres (exhausted connections
    # after a bad multi-worker deploy must not prevent /health from answering,
    # or CodeDeploy ValidateService fails forever and HEALTH_CONSTRAINTS rolls back).
    import logging
    import os
    import threading
    import time

    log = logging.getLogger("uvicorn.error")
    try:
        init_pool(min_size=0, max_size=5)
    except Exception:
        log.exception("Database pool failed to open — /health still available; DB routes will error until pool recovers")

    # Only one process should warm: uvicorn workers each run lifespan.
    warm_lock = "/tmp/welllabs-village-warm.lock"
    should_warm = False
    try:
        fd = os.open(warm_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        should_warm = True
    except FileExistsError:
        try:
            age = time.time() - os.path.getmtime(warm_lock)
            if age > 3600:
                os.unlink(warm_lock)
                fd = os.open(warm_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                should_warm = True
        except OSError:
            should_warm = False

    if should_warm:
        try:
            from app.shared.watersheds import warm_village_name_index

            threading.Thread(
                target=warm_village_name_index, name="village-index-warm", daemon=True
            ).start()
        except Exception:
            log.exception("Village index warm failed to start (non-fatal)")

    try:
        yield
    finally:
        close_pool()
        await users_async_engine.dispose()


app = FastAPI(title="DDA Product API", version="0.3.0", lifespan=lifespan)


def _oauth_callback_login_redirect(request: Request, detail: str = "") -> HTMLResponse:
    """Browser-friendly redirect to login after OAuth callback errors."""
    params = "oauth_error=1"
    if detail:
        params += f"&oauth_detail={detail[:120]}"
    login = f"{request_public_app_base(request)}/login?{params}"
    safe_meta = html.escape(login, quote=True)
    safe_js = json.dumps(login)
    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0;url={safe_meta}">
<title>Sign-in failed</title>
</head><body>
<p>Google sign-in could not be completed. Redirecting to login…</p>
<script>window.location.replace({safe_js});</script>
</body></html>""",
        status_code=200,
        headers={"Cache-Control": "no-store", "CDN-Cache-Control": "no-store"},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Never leave users on the raw callback URL with JSON errors."""
    if "google/callback" not in request.url.path:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return _oauth_callback_login_redirect(request, detail)

# Honor X-Forwarded-* from the Vite/SvelteKit /api proxy (localhost:5173/5174)
app.add_middleware(ForwardedHostMiddleware)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Accounts module — auth, users, organizations. Shared across all other modules.
app.include_router(auth.router, prefix="/api/accounts/auth", tags=["accounts:auth"])
app.include_router(users.router, prefix="/api/accounts/users", tags=["accounts:users"])
app.include_router(orgs.router, prefix="/api/accounts/orgs", tags=["accounts:orgs"])
app.include_router(qfield_account.router, prefix="/api/accounts/qfield", tags=["accounts:qfield"])

# Diagnose module — watershed-scoped mapping, observation zones, field notes, QField sync.
app.include_router(layers.router, prefix="/api/diagnose/layers", tags=["diagnose:layers"])
app.include_router(diagnosis.router, prefix="/api/diagnose/projects", tags=["diagnose:projects"])
app.include_router(watersheds.router, prefix="/api/diagnose/watersheds", tags=["diagnose:watersheds"])
app.include_router(
    observation_zones.router, prefix="/api/diagnose/observation-zones", tags=["diagnose:observation-zones"]
)
app.include_router(field_notes.router, prefix="/api/diagnose/field-notes", tags=["diagnose:field-notes"])
app.include_router(hypotheses.router, prefix="/api/diagnose/hypotheses", tags=["diagnose:hypotheses"])
app.include_router(qfield.router, prefix="/api/diagnose/qfield", tags=["diagnose:qfield"])

# Design and Assess modules
app.include_router(design.router, prefix="/api/design", tags=["design"])
app.include_router(assess.router, prefix="/api/assess", tags=["assess"])
app.include_router(mel_projects.router, prefix="/api/assess", tags=["assess:mel-projects"])
app.include_router(mel.router, prefix="/api/assess", tags=["assess:mel"])
app.include_router(
    assess_access.router,
    prefix="/api/assess/projects",
    tags=["assess:access"],
)
app.include_router(
    assess_reports.router,
    prefix="/api/assess/projects",
    tags=["assess:reports"],
)
if metabase_router is not None:
    app.include_router(
        metabase_router.router,
        prefix="/api/assess/metabase",
        tags=["assess:metabase"],
    )


@app.get("/health")
def health():
    return {"status": "ok"}

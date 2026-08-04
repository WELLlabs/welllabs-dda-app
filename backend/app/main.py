from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.modules.accounts.routers import auth, orgs, qfield_account, users
from app.modules.assess.routers import access as assess_access
from app.modules.assess.routers import assess, reports as assess_reports
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
from app.shared.forwarded_host import ForwardedHostMiddleware
from app.shared.users.db import engine as users_async_engine

# Metabase router is optional until Assess ships the module.
try:
    from app.modules.assess.routers import metabase as metabase_router
except ImportError:  # pragma: no cover
    metabase_router = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_pool(min_size=2, max_size=10)
    try:
        yield
    finally:
        close_pool()
        await users_async_engine.dispose()


app = FastAPI(title="DDA Product API", version="0.3.0", lifespan=lifespan)

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

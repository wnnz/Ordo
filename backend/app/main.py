from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    admin,
    api_keys,
    auth,
    models,
    public,
    scripts,
    system_settings,
    workflows,
    workspaces,
)
from app.core.config import get_settings
from app.middleware.body_limit import RequestBodyLimitMiddleware
from app.observability import install_observability

settings = get_settings()
app = FastAPI(
    title="Ordo API",
    version="0.1.0",
    description="Multi-workspace AI workflow and script management platform",
)
install_observability(app)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(workspaces.router, prefix="/api/v1")
app.include_router(scripts.router, prefix="/api/v1")
app.include_router(workflows.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")
app.include_router(api_keys.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(system_settings.router, prefix="/api/v1")
app.include_router(public.router, prefix="/v1")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}

from fastapi import FastAPI

from app.api import api_router

# Everything lives under /api so the SPA and API can share one origin in production.
app = FastAPI(
    title="PJ Tricia API",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url=None,
)
app.include_router(api_router, prefix="/api")

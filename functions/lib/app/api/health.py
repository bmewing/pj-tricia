from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import SessionDep

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]


@router.get("/health")
async def health(session: SessionDep) -> HealthResponse:
    # Always 200: restarting the web service won't fix a database outage.
    try:
        await session.execute(text("SELECT 1"))
    except (OSError, TimeoutError, SQLAlchemyError):
        return HealthResponse(status="degraded", database="unavailable")
    return HealthResponse(status="ok", database="ok")

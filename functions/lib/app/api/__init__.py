from fastapi import APIRouter

from app.api import events, groups, health, live, me, questions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(me.router)
api_router.include_router(groups.router)
api_router.include_router(events.router)
api_router.include_router(questions.router)
api_router.include_router(live.router)

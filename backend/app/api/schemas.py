"""Shapes shared by several routers."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import Event, EventStatus, User


class PersonRead(BaseModel):
    id: uuid.UUID
    display_name: str
    avatar_url: str | None

    @classmethod
    def of(cls, user: User) -> "PersonRead":
        return cls(id=user.id, display_name=user.display_name, avatar_url=user.avatar_url)


class EventBrief(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    title: str
    starts_at: datetime
    duration_minutes: int
    status: EventStatus
    host: PersonRead | None
    players: int  # yes or maybe, as players

    @classmethod
    def of(cls, event: Event, host: User | None, players: int) -> "EventBrief":
        return cls(
            id=event.id,
            group_id=event.group_id,
            title=event.title,
            starts_at=event.starts_at,
            duration_minutes=event.duration_minutes,
            status=event.status,
            host=PersonRead.of(host) if host else None,
            players=players,
        )

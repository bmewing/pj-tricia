"""Trivia nights: when they are, who's coming, who hosts, and where the game is."""

import secrets
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import string_enum


def new_spectate_token() -> str:
    return secrets.token_urlsafe(12)


class EventStatus(StrEnum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    LIVE = "live"
    FINISHED = "finished"


class StepPhase(StrEnum):
    OPEN = "open"  # taking answers
    CLOSED = "closed"  # answers locked, correct answer shown


class RsvpResponse(StrEnum):
    YES = "yes"
    MAYBE = "maybe"
    NO = "no"


class AttendeeRole(StrEnum):
    PLAYER = "player"  # one account is one team
    SPECTATOR = "spectator"  # watches, can't answer


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="duration_positive"),
        Index("ix_events_group_starts", "group_id", "starts_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=120)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[EventStatus] = mapped_column(
        string_enum(EventStatus), default=EventStatus.SCHEDULED
    )
    # Writes the questions and runs the game; doesn't play.
    host_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Anyone signed in with /watch/<token> can join as a spectator, member or not.
    spectate_token: Mapped[str] = mapped_column(String(32), unique=True, default=new_spectate_token)
    # The game: which step of app.game.steps the host is on, and whether it takes answers.
    current_step: Mapped[int | None] = mapped_column(Integer)
    step_phase: Mapped[StepPhase | None] = mapped_column(string_enum(StepPhase))
    # Bumped on every change anyone could see in the game, so polls can skip unchanged state.
    version: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventAttendee(Base):
    __tablename__ = "event_attendees"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    response: Mapped[RsvpResponse] = mapped_column(string_enum(RsvpResponse))
    role: Mapped[AttendeeRole] = mapped_column(string_enum(AttendeeRole))
    # Shown instead of the display name, e.g. "The Smiths".
    team_name: Mapped[str | None] = mapped_column(String(60))
    responded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

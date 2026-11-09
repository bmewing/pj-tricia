"""The host's questions for an event, and each team's answers."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import string_enum


class QuestionKind(StrEnum):
    MC = "mc"  # rounds 1-3: four choices, auto-graded
    DOUBLE_DARE = "double_dare"  # one at the end of each of rounds 1-3, free-form
    FREE = "free"  # round 4, free-form
    FINAL = "final"  # the wager question at the end of round 4


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("round BETWEEN 1 AND 4", name="round_range"),
        # One double dare per round 1-3 and one final, per event.
        Index(
            "uq_questions_one_special_per_round",
            "event_id",
            "round",
            unique=True,
            postgresql_where=text("kind IN ('double_dare', 'final')"),
        ),
        Index("ix_questions_event_order", "event_id", "round", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    round: Mapped[int] = mapped_column(Integer)
    kind: Mapped[QuestionKind] = mapped_column(string_enum(QuestionKind))
    # Order within the round (mc and free only; the special ones come last).
    position: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    # Multiple choice: four options, and which one is right.
    choices: Mapped[list[str] | None] = mapped_column(JSONB)
    correct_choice: Mapped[int | None] = mapped_column(Integer)
    # Free-form: what the host is looking for.
    answer_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("question_id", "user_id"),
        CheckConstraint("wager IS NULL OR wager >= 0", name="wager_not_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    choice: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str | None] = mapped_column(String(500))
    # Double dare: sat it out.
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Final: points staked, set during the wager step.
    wager: Mapped[int | None] = mapped_column(Integer)
    # Null: not graded yet. Multiple choice is graded on submit; free-form by the host, or
    # on submit when it matches the answer exactly.
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

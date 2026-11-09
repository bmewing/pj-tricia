"""Groups and who's in them."""

import secrets
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import string_enum


def new_invite_code() -> str:
    return secrets.token_urlsafe(9)


class GroupRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    # Anyone signed in who opens /join/<code> can join. Runners can make a new one.
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, default=new_invite_code)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        # One owner per group.
        Index(
            "uq_group_members_one_owner",
            "group_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[GroupRole] = mapped_column(string_enum(GroupRole))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

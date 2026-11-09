"""Who can see and do what in groups and events."""

import uuid
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AttendeeRole,
    Event,
    EventAttendee,
    Group,
    GroupMember,
    GroupRole,
    RsvpResponse,
    User,
)

GROUP_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
EVENT_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
RUNS_GROUP = (GroupRole.OWNER, GroupRole.ADMIN)

GameRole = Literal["host", "player", "spectator"]


async def membership(
    session: AsyncSession, group_id: uuid.UUID, user: User
) -> tuple[Group, GroupMember]:
    """The group and your place in it. Groups you aren't in look like they don't exist."""
    row = (
        await session.execute(
            select(Group, GroupMember)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(Group.id == group_id, GroupMember.user_id == user.id)
        )
    ).first()
    if row is None:
        raise GROUP_NOT_FOUND
    group, member = row
    return group, member


def runs_group(member: GroupMember | None) -> bool:
    return member is not None and member.role in RUNS_GROUP


def require_runner(member: GroupMember | None) -> None:
    """Owners and admins run the group: its details, events and invite link."""
    if not runs_group(member):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner and admins can do that.")


def require_owner(member: GroupMember) -> None:
    if member.role != GroupRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the group's owner can do that.")


@dataclass
class EventAccess:
    event: Event
    group: Group
    member: GroupMember | None  # None: a spectator from outside the group
    attendee: EventAttendee | None
    user: User

    @property
    def is_host(self) -> bool:
        return self.event.host_user_id == self.user.id

    @property
    def can_manage(self) -> bool:
        return runs_group(self.member)

    @property
    def game_role(self) -> GameRole:
        if self.is_host:
            return "host"
        if is_player(self.attendee):
            return "player"
        return "spectator"


def is_player(attendee: EventAttendee | None) -> bool:
    return (
        attendee is not None
        and attendee.role == AttendeeRole.PLAYER
        and attendee.response != RsvpResponse.NO
    )


async def event_access(session: AsyncSession, event_id: uuid.UUID, user: User) -> EventAccess:
    """The event as you can see it: group members, and spectators who joined by link.
    Anyone else gets a 404."""
    row = (
        await session.execute(
            select(Event, Group, GroupMember, EventAttendee)
            .join(Group, Group.id == Event.group_id)
            .outerjoin(
                GroupMember,
                (GroupMember.group_id == Group.id) & (GroupMember.user_id == user.id),
            )
            .outerjoin(
                EventAttendee,
                (EventAttendee.event_id == Event.id) & (EventAttendee.user_id == user.id),
            )
            .where(Event.id == event_id)
        )
    ).first()
    if row is None:
        raise EVENT_NOT_FOUND
    event, group, member, attendee = row
    if member is None and attendee is None:
        raise EVENT_NOT_FOUND
    return EventAccess(event, group, member, attendee, user)


def require_host(access: EventAccess) -> None:
    if not access.is_host:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the host can do that.")


async def bump(session: AsyncSession, event_id: uuid.UUID) -> None:
    """Something in the game changed: polls should fetch it."""
    await session.execute(
        update(Event).where(Event.id == event_id).values(version=Event.version + 1)
    )

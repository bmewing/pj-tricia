"""Groups: making them, joining by link, roles, and their events."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import membership, require_owner, require_runner
from app.api.schemas import EventBrief, PersonRead
from app.auth import CurrentUser
from app.db import SessionDep
from app.models import (
    AttendeeRole,
    Event,
    EventAttendee,
    EventStatus,
    Group,
    GroupMember,
    GroupRole,
    RsvpResponse,
    User,
)
from app.models.group import new_invite_code

router = APIRouter(tags=["groups"])

GroupName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
RECENT_EVENTS = 5
# An event counts as upcoming until this long after it starts, or while it's live.
STILL_UPCOMING = timedelta(hours=6)


class GroupSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    my_role: GroupRole
    member_count: int
    next_event: EventBrief | None


class MemberRead(BaseModel):
    person: PersonRead
    role: GroupRole
    joined_at: datetime


class GroupRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    invite_code: str
    my_role: GroupRole
    members: list[MemberRead]
    upcoming: list[EventBrief]
    recent: list[EventBrief]


class GroupCreate(BaseModel):
    name: GroupName
    description: Description | None = None


class GroupUpdate(BaseModel):
    name: GroupName | None = None
    description: Description | None = None


class MemberUpdate(BaseModel):
    """`owner` hands the group over; the current owner becomes an admin."""

    role: GroupRole


class JoinPreview(BaseModel):
    group_id: uuid.UUID
    name: str
    description: str | None
    member_count: int
    already_member: bool


async def event_briefs(session: AsyncSession, events: list[Event]) -> list[EventBrief]:
    ids = [e.id for e in events]
    players: dict[uuid.UUID, int] = defaultdict(int)
    hosts: dict[uuid.UUID, User] = {}
    if ids:
        counts = await session.execute(
            select(EventAttendee.event_id, func.count())
            .where(
                EventAttendee.event_id.in_(ids),
                EventAttendee.role == AttendeeRole.PLAYER,
                EventAttendee.response != RsvpResponse.NO,
            )
            .group_by(EventAttendee.event_id)
        )
        players.update({event_id: count for event_id, count in counts})
        host_ids = {e.host_user_id for e in events if e.host_user_id}
        if host_ids:
            hosts = {
                u.id: u for u in await session.scalars(select(User).where(User.id.in_(host_ids)))
            }
    return [
        EventBrief.of(e, hosts.get(e.host_user_id) if e.host_user_id else None, players[e.id])
        for e in events
    ]


def _upcoming_filter(group_id: uuid.UUID) -> ColumnElement[bool]:
    cutoff = datetime.now(UTC) - STILL_UPCOMING
    return (
        (Event.group_id == group_id)
        & ((Event.starts_at >= cutoff) | (Event.status == EventStatus.LIVE))
        & (Event.status != EventStatus.FINISHED)
    )


@router.get("/groups")
async def list_groups(user: CurrentUser, session: SessionDep) -> list[GroupSummary]:
    member_count = (
        select(func.count())
        .where(GroupMember.group_id == Group.id)
        .correlate(Group)
        .scalar_subquery()
    )
    rows = await session.execute(
        select(Group, GroupMember.role, member_count)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.user_id == user.id)
        .order_by(func.lower(Group.name))
    )
    result = []
    for group, role, count in rows:
        next_event = await session.scalar(
            select(Event)
            .where(_upcoming_filter(group.id), Event.status != EventStatus.CANCELLED)
            .order_by(Event.starts_at)
            .limit(1)
        )
        briefs = await event_briefs(session, [next_event] if next_event else [])
        result.append(
            GroupSummary(
                id=group.id,
                name=group.name,
                description=group.description,
                my_role=role,
                member_count=count,
                next_event=briefs[0] if briefs else None,
            )
        )
    return result


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(body: GroupCreate, user: CurrentUser, session: SessionDep) -> GroupRead:
    group = Group(name=body.name, description=body.description or None)
    session.add(group)
    await session.flush()
    session.add(GroupMember(group_id=group.id, user_id=user.id, role=GroupRole.OWNER))
    await session.commit()
    return await read_group(group.id, user, session)


@router.get("/groups/{group_id}")
async def read_group(group_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> GroupRead:
    group, me = await membership(session, group_id, user)
    members = await session.execute(
        select(GroupMember, User)
        .join(User, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group.id)
        .order_by(GroupMember.joined_at)
    )
    upcoming = list(
        await session.scalars(
            select(Event).where(_upcoming_filter(group.id)).order_by(Event.starts_at)
        )
    )
    upcoming_ids = {e.id for e in upcoming}
    recent = [
        e
        for e in await session.scalars(
            select(Event)
            .where(Event.group_id == group.id)
            .order_by(Event.starts_at.desc())
            .limit(RECENT_EVENTS + len(upcoming_ids))
        )
        if e.id not in upcoming_ids
    ][:RECENT_EVENTS]
    return GroupRead(
        id=group.id,
        name=group.name,
        description=group.description,
        invite_code=group.invite_code,
        my_role=me.role,
        members=[
            MemberRead(person=PersonRead.of(person), role=member.role, joined_at=member.joined_at)
            for member, person in members
        ],
        upcoming=await event_briefs(session, upcoming),
        recent=await event_briefs(session, recent),
    )


@router.patch("/groups/{group_id}")
async def update_group(
    group_id: uuid.UUID, changes: GroupUpdate, user: CurrentUser, session: SessionDep
) -> GroupRead:
    group, me = await membership(session, group_id, user)
    require_runner(me)
    if changes.name is not None:
        group.name = changes.name
    if "description" in changes.model_fields_set:
        group.description = changes.description or None
    await session.commit()
    return await read_group(group.id, user, session)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    group, me = await membership(session, group_id, user)
    require_owner(me)
    await session.delete(group)
    await session.commit()


@router.post("/groups/{group_id}/invite-code")
async def new_group_invite_code(
    group_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> GroupRead:
    """Make a new invite link; the old one stops working."""
    group, me = await membership(session, group_id, user)
    require_runner(me)
    group.invite_code = new_invite_code()
    await session.commit()
    return await read_group(group.id, user, session)


async def _group_by_code(session: AsyncSession, code: str) -> Group:
    group = await session.scalar(select(Group).where(Group.invite_code == code))
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That invite link doesn't work anymore.")
    return group


@router.get("/join/{code}")
async def preview_join(code: str, user: CurrentUser, session: SessionDep) -> JoinPreview:
    group = await _group_by_code(session, code)
    count = await session.scalar(select(func.count()).where(GroupMember.group_id == group.id))
    already = await session.get(GroupMember, (group.id, user.id))
    return JoinPreview(
        group_id=group.id,
        name=group.name,
        description=group.description,
        member_count=count or 0,
        already_member=already is not None,
    )


@router.post("/join/{code}")
async def join_group(code: str, user: CurrentUser, session: SessionDep) -> GroupRead:
    group = await _group_by_code(session, code)
    await session.execute(
        insert(GroupMember)
        .values(group_id=group.id, user_id=user.id, role=GroupRole.MEMBER)
        .on_conflict_do_nothing()
    )
    await session.commit()
    return await read_group(group.id, user, session)


async def _member(session: AsyncSession, group_id: uuid.UUID, user_id: uuid.UUID) -> GroupMember:
    member = await session.get(GroupMember, (group_id, user_id))
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a member of this group")
    return member


@router.patch("/groups/{group_id}/members/{user_id}")
async def change_member_role(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    body: MemberUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> GroupRead:
    """Only the owner makes admins, turns them back into members, or hands the group over."""
    group, me = await membership(session, group_id, user)
    require_owner(me)
    target = await _member(session, group.id, user_id)
    if target.user_id == user.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Hand the group to someone else to change your role."
        )
    if body.role == GroupRole.OWNER:
        me.role = GroupRole.ADMIN
        await session.flush()  # one owner at a time
    target.role = body.role
    await session.commit()
    return await read_group(group.id, user, session)


@router.delete("/groups/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Leave (your own id), or remove someone. Admins can remove members, not other admins;
    the owner can remove anyone. Their RSVPs for events still to come go with them."""
    group, me = await membership(session, group_id, user)
    target = await _member(session, group.id, user_id)
    leaving = target.user_id == user.id
    if leaving and me.role == GroupRole.OWNER:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Hand the group to someone else before you leave."
        )
    may_remove = me.role == GroupRole.OWNER or (
        me.role == GroupRole.ADMIN and target.role == GroupRole.MEMBER
    )
    if not leaving and not may_remove:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't remove this member.")
    scheduled = select(Event.id).where(
        Event.group_id == group.id, Event.status == EventStatus.SCHEDULED
    )
    await session.execute(
        delete(EventAttendee).where(
            EventAttendee.user_id == target.user_id, EventAttendee.event_id.in_(scheduled)
        )
    )
    await session.delete(target)
    await session.commit()

"""Events: scheduling them, RSVPs, picking the host, and spectating by link."""

import random
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import (
    EventAccess,
    GameRole,
    bump,
    event_access,
    membership,
    require_runner,
)
from app.api.schemas import PersonRead
from app.auth import CurrentUser
from app.db import SessionDep
from app.game.steps import problems
from app.models import (
    AttendeeRole,
    Event,
    EventAttendee,
    EventStatus,
    Group,
    GroupMember,
    Question,
    RsvpResponse,
    User,
)

router = APIRouter(tags=["events"])

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
TeamName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]
Duration = Annotated[int, Field(ge=15, le=12 * 60)]

NOT_SCHEDULED = HTTPException(
    status.HTTP_409_CONFLICT, "That can't change once the game has started."
)
QUESTIONS_EXIST = HTTPException(
    status.HTTP_409_CONFLICT,
    "The current host has written questions. Say whether to keep them or clear them.",
)


class AttendeeRead(BaseModel):
    person: PersonRead
    response: RsvpResponse
    role: AttendeeRole
    team_name: str | None


class MyPlace(BaseModel):
    is_member: bool
    can_manage: bool  # owner or admin of the group
    game_role: GameRole
    attendee: AttendeeRead | None


class EventRead(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    group_name: str
    title: str
    starts_at: datetime
    duration_minutes: int
    notes: str | None
    status: EventStatus
    host: PersonRead | None
    attendees: list[AttendeeRead]
    me: MyPlace
    spectate_token: str | None  # members only
    # The host's own view of their questions; null for everyone else.
    question_count: int | None
    problems: list[str] | None


class EventCreate(BaseModel):
    title: Title
    starts_at: datetime
    duration_minutes: Duration = 120
    notes: Notes | None = None


class EventUpdate(BaseModel):
    title: Title | None = None
    starts_at: datetime | None = None
    duration_minutes: Duration | None = None
    notes: Notes | None = None
    cancelled: bool | None = None


class Rsvp(BaseModel):
    response: RsvpResponse
    role: AttendeeRole = AttendeeRole.PLAYER
    team_name: TeamName | None = None


class HostChange(BaseModel):
    """Null keeps the default: fine when there are no questions yet, refused otherwise."""

    clear_questions: bool | None = None


class HostAssign(HostChange):
    user_id: uuid.UUID


class WatchPreview(BaseModel):
    event_id: uuid.UUID
    title: str
    group_name: str
    starts_at: datetime
    status: EventStatus
    already_in: bool


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the time with its offset.")
    return value


async def read_event_for(session: AsyncSession, access: EventAccess) -> EventRead:
    event = access.event
    rows = await session.execute(
        select(EventAttendee, User)
        .join(User, User.id == EventAttendee.user_id)
        .where(EventAttendee.event_id == event.id)
        .order_by(EventAttendee.responded_at, User.id)
    )
    attendees = [
        AttendeeRead(
            person=PersonRead.of(person),
            response=attendee.response,
            role=attendee.role,
            team_name=attendee.team_name,
        )
        for attendee, person in rows
    ]
    host = await session.get(User, event.host_user_id) if event.host_user_id else None
    mine = next((a for a in attendees if a.person.id == access.user.id), None)
    question_count = None
    found = None
    if access.is_host:
        questions = list(
            await session.scalars(select(Question).where(Question.event_id == event.id))
        )
        question_count = len(questions)
        found = problems(questions)
    return EventRead(
        id=event.id,
        group_id=event.group_id,
        group_name=access.group.name,
        title=event.title,
        starts_at=event.starts_at,
        duration_minutes=event.duration_minutes,
        notes=event.notes,
        status=event.status,
        host=PersonRead.of(host) if host else None,
        attendees=attendees,
        me=MyPlace(
            is_member=access.member is not None,
            can_manage=access.can_manage,
            game_role=access.game_role,
            attendee=mine,
        ),
        spectate_token=event.spectate_token if access.member is not None else None,
        question_count=question_count,
        problems=found,
    )


async def _read(session: AsyncSession, event_id: uuid.UUID, user: User) -> EventRead:
    return await read_event_for(session, await event_access(session, event_id, user))


@router.post("/groups/{group_id}/events", status_code=status.HTTP_201_CREATED)
async def create_event(
    group_id: uuid.UUID, body: EventCreate, user: CurrentUser, session: SessionDep
) -> EventRead:
    group, me = await membership(session, group_id, user)
    require_runner(me)
    event = Event(
        group_id=group.id,
        title=body.title,
        starts_at=_aware(body.starts_at),
        duration_minutes=body.duration_minutes,
        notes=body.notes or None,
    )
    session.add(event)
    await session.commit()
    return await _read(session, event.id, user)


@router.get("/events/{event_id}")
async def read_event(event_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> EventRead:
    return await _read(session, event_id, user)


@router.patch("/events/{event_id}")
async def update_event(
    event_id: uuid.UUID, changes: EventUpdate, user: CurrentUser, session: SessionDep
) -> EventRead:
    access = await event_access(session, event_id, user)
    require_runner(access.member)
    event = access.event
    if event.status not in (EventStatus.SCHEDULED, EventStatus.CANCELLED):
        raise NOT_SCHEDULED
    if changes.title is not None:
        event.title = changes.title
    if changes.starts_at is not None:
        event.starts_at = _aware(changes.starts_at)
    if changes.duration_minutes is not None:
        event.duration_minutes = changes.duration_minutes
    if "notes" in changes.model_fields_set:
        event.notes = changes.notes or None
    if changes.cancelled is not None:
        event.status = EventStatus.CANCELLED if changes.cancelled else EventStatus.SCHEDULED
    await session.commit()
    return await _read(session, event_id, user)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    access = await event_access(session, event_id, user)
    require_runner(access.member)
    if access.event.status == EventStatus.LIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "End the game before deleting the event.")
    await session.delete(access.event)
    await session.commit()


@router.put("/events/{event_id}/rsvp")
async def rsvp(
    event_id: uuid.UUID, body: Rsvp, user: CurrentUser, session: SessionDep
) -> EventRead:
    """Say whether you're coming, and as a player (your account is your team) or to watch.
    Players can join while the game is on. Only group members can play."""
    access = await event_access(session, event_id, user)
    event = access.event
    if event.status in (EventStatus.CANCELLED, EventStatus.FINISHED):
        raise HTTPException(status.HTTP_409_CONFLICT, "This event is over.")
    role = body.role
    if role == AttendeeRole.PLAYER and access.member is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only group members can play.")
    if role == AttendeeRole.PLAYER and access.is_host:
        raise HTTPException(status.HTTP_409_CONFLICT, "The host can't play.")
    attendee = access.attendee
    if attendee is None:
        attendee = EventAttendee(event_id=event.id, user_id=user.id)
        session.add(attendee)
    attendee.response = body.response
    attendee.role = role
    attendee.team_name = body.team_name or None
    await bump(session, event.id)  # the lobby and the game list who's playing
    await session.commit()
    return await _read(session, event_id, user)


async def _set_host(
    session: AsyncSession, access: EventAccess, new_host: uuid.UUID | None, change: HostChange
) -> None:
    event = access.event
    if event.status != EventStatus.SCHEDULED:
        raise NOT_SCHEDULED
    if new_host == event.host_user_id:
        return
    if event.host_user_id is not None:
        written = await session.scalar(select(func.count()).where(Question.event_id == event.id))
        if written and change.clear_questions is None:
            raise QUESTIONS_EXIST
        if written and change.clear_questions:
            await session.execute(delete(Question).where(Question.event_id == event.id))
    event.host_user_id = new_host
    if new_host is not None:
        # The host runs the game rather than playing it.
        attendee = await session.get(EventAttendee, (event.id, new_host))
        if attendee is None:
            session.add(
                EventAttendee(
                    event_id=event.id,
                    user_id=new_host,
                    response=RsvpResponse.YES,
                    role=AttendeeRole.SPECTATOR,
                )
            )
        else:
            attendee.response = RsvpResponse.YES
            attendee.role = AttendeeRole.SPECTATOR
    await bump(session, event.id)
    await session.commit()


@router.post("/events/{event_id}/host/volunteer")
async def volunteer_to_host(
    event_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> EventRead:
    access = await event_access(session, event_id, user)
    if access.member is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only group members can host.")
    if access.event.host_user_id not in (None, user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Someone is already hosting.")
    await _set_host(session, access, user.id, HostChange())
    return await _read(session, event_id, user)


@router.put("/events/{event_id}/host")
async def assign_host(
    event_id: uuid.UUID, body: HostAssign, user: CurrentUser, session: SessionDep
) -> EventRead:
    access = await event_access(session, event_id, user)
    require_runner(access.member)
    if await session.get(GroupMember, (access.group.id, body.user_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a member of this group")
    await _set_host(session, access, body.user_id, body)
    return await _read(session, event_id, user)


@router.post("/events/{event_id}/host/random")
async def pick_random_host(
    event_id: uuid.UUID, body: HostChange, user: CurrentUser, session: SessionDep
) -> EventRead:
    """Pick a host at random from the members who said yes as players."""
    access = await event_access(session, event_id, user)
    require_runner(access.member)
    candidates = list(
        await session.scalars(
            select(EventAttendee.user_id)
            .join(
                GroupMember,
                (GroupMember.user_id == EventAttendee.user_id)
                & (GroupMember.group_id == access.group.id),
            )
            .where(
                EventAttendee.event_id == event_id,
                EventAttendee.response == RsvpResponse.YES,
                EventAttendee.role == AttendeeRole.PLAYER,
            )
        )
    )
    if not candidates:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nobody has said yes as a player yet.")
    await _set_host(session, access, random.choice(candidates), body)
    return await _read(session, event_id, user)


@router.post("/events/{event_id}/host/clear")
async def clear_host(
    event_id: uuid.UUID, body: HostChange, user: CurrentUser, session: SessionDep
) -> EventRead:
    """The host steps down, or a runner takes them off."""
    access = await event_access(session, event_id, user)
    if not access.is_host:
        require_runner(access.member)
    await _set_host(session, access, None, body)
    return await _read(session, event_id, user)


async def _event_by_token(session: AsyncSession, token: str) -> Event:
    event = await session.scalar(select(Event).where(Event.spectate_token == token))
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That link doesn't work.")
    return event


@router.get("/watch/{token}")
async def preview_watch(token: str, user: CurrentUser, session: SessionDep) -> WatchPreview:
    event = await _event_by_token(session, token)
    group = await session.get(Group, event.group_id)
    assert group is not None
    member = await session.get(GroupMember, (group.id, user.id))
    attendee = await session.get(EventAttendee, (event.id, user.id))
    return WatchPreview(
        event_id=event.id,
        title=event.title,
        group_name=group.name,
        starts_at=event.starts_at,
        status=event.status,
        already_in=member is not None or attendee is not None,
    )


@router.post("/watch/{token}")
async def join_as_spectator(token: str, user: CurrentUser, session: SessionDep) -> EventRead:
    event = await _event_by_token(session, token)
    if await session.get(EventAttendee, (event.id, user.id)) is None:
        session.add(
            EventAttendee(
                event_id=event.id,
                user_id=user.id,
                response=RsvpResponse.YES,
                role=AttendeeRole.SPECTATOR,
            )
        )
        await session.commit()
    return await _read(session, event.id, user)

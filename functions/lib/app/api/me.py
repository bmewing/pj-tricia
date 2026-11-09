import uuid
from typing import Annotated

from fastapi import APIRouter, status
from pydantic import AfterValidator, BaseModel, StringConstraints
from sqlalchemy import delete, select

from app.auth import CurrentUser
from app.db import SessionDep
from app.models import Group, GroupMember, GroupRole, User

router = APIRouter(prefix="/me", tags=["me"])


def single_spaces(value: str) -> str:
    return " ".join(value.split())


DisplayName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    AfterValidator(single_spaces),
]


class UserRead(BaseModel):
    id: uuid.UUID
    email: str | None
    display_name: str
    avatar_url: str | None

    @classmethod
    def of(cls, user: User) -> "UserRead":
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
        )


class UserUpdate(BaseModel):
    display_name: DisplayName


@router.get("")
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.of(user)


@router.patch("")
async def update_me(changes: UserUpdate, user: CurrentUser, session: SessionDep) -> UserRead:
    user.display_name = changes.display_name
    await session.commit()
    return UserRead.of(user)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(user: CurrentUser, session: SessionDep) -> None:
    """Removes our data only; the Kinde login itself remains until deleted there. Groups
    they own pass to the longest-serving admin, else member; empty ones are deleted."""
    owned = await session.scalars(
        select(GroupMember).where(
            GroupMember.user_id == user.id, GroupMember.role == GroupRole.OWNER
        )
    )
    for ownership in list(owned):
        group_id = ownership.group_id
        await session.delete(ownership)
        await session.flush()
        heir = await session.scalar(
            select(GroupMember)
            .where(GroupMember.group_id == group_id)
            .order_by(
                (GroupMember.role == GroupRole.ADMIN).desc(),
                GroupMember.joined_at,
                GroupMember.user_id,
            )
            .limit(1)
        )
        if heir is None:
            await session.execute(delete(Group).where(Group.id == group_id))
        else:
            heir.role = GroupRole.OWNER
            await session.flush()
    await session.delete(user)
    await session.commit()

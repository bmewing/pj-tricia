from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends
from sqlalchemy import MetaData, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import Settings, get_settings

# Stable constraint names so Alembic autogenerate produces predictable migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_engine_for(settings: Settings) -> AsyncEngine:
    if not settings.serverless:
        return create_async_engine(
            settings.database_url, pool_pre_ping=True, connect_args={"timeout": 5}
        )
    # Functions are short-lived and can be frozen between requests, so keep no pool; and
    # a transaction pooler (Neon, Supabase) keeps no prepared statements between transactions.
    url = make_url(settings.database_url).update_query_dict({"prepared_statement_cache_size": "0"})
    connect_args: dict[str, Any] = {
        "timeout": 5,
        "statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    }
    return create_async_engine(url, poolclass=NullPool, connect_args=connect_args)


engine = create_engine_for(get_settings())
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]

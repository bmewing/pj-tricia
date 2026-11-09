"""Authentication: verify Kinde access tokens and resolve the calling user."""

import asyncio
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import SessionDep
from app.models import User

bearer = HTTPBearer(auto_error=False)

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


@lru_cache
def get_jwks_client() -> jwt.PyJWKClient:
    """Kinde's signing keys, fetched once and cached in memory."""
    domain = get_settings().kinde_domain
    if not domain:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "KINDE_DOMAIN is not set")
    return jwt.PyJWKClient(f"{domain}/.well-known/jwks.json", lifespan=3600)


async def get_token_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    jwks_client: Annotated[jwt.PyJWKClient, Depends(get_jwks_client)],
) -> dict[str, Any]:
    if credentials is None:
        raise UNAUTHORIZED
    token = credentials.credentials
    settings = get_settings()
    try:
        # The key lookup may hit the network on a cache miss, so keep it off the event loop.
        signing_key = await asyncio.to_thread(jwks_client.get_signing_key_from_jwt, token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.kinde_audience,
            issuer=settings.kinde_domain,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Could not reach the sign-in provider"
        ) from exc
    except (jwt.PyJWKClientError, jwt.InvalidTokenError) as exc:
        raise UNAUTHORIZED from exc
    return claims


ClaimsDep = Annotated[dict[str, Any], Depends(get_token_claims)]

# How stale last_seen_at may get before a request updates it, so most requests don't write.
LAST_SEEN_GRANULARITY = timedelta(minutes=5)


def default_display_name(claims: dict[str, Any]) -> str:
    full_name = " ".join(
        part for part in (claims.get("given_name"), claims.get("family_name")) if part
    )
    full_name = " ".join(full_name.split())
    if full_name:
        return full_name[:80]
    email = claims.get("email")
    if email:
        return str(email).split("@")[0][:80]
    return "Player"


async def get_current_user(claims: ClaimsDep, session: SessionDep) -> User:
    """Return the calling user, creating their record on first sight."""
    kinde_id = claims["sub"]
    email = claims.get("email")
    user = await session.scalar(select(User).where(User.kinde_id == kinde_id))
    if user is None:
        # A second first request for the same person racing this one is a no-op.
        await session.execute(
            insert(User)
            .values(
                kinde_id=kinde_id,
                email=email,
                display_name=default_display_name(claims),
                avatar_url=claims.get("picture"),
            )
            .on_conflict_do_nothing()
        )
        await session.commit()
        user = await session.scalar(select(User).where(User.kinde_id == kinde_id))
        if user is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not set up account")
    changed = False
    if email and user.email != email:
        # Kinde owns the email address; keep ours in step if it changes there.
        user.email = email
        changed = True
    now = datetime.now(UTC)
    if user.last_seen_at is None or now - user.last_seen_at >= LAST_SEEN_GRANULARITY:
        user.last_seen_at = now
        changed = True
    if changed:
        await session.commit()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

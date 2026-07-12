from typing import Annotated, Optional

from fastapi import Depends, Header

from app.cache.noop_cache import NoopCache, get_noop_cache
from app.core.exceptions import UnauthorizedException
from app.core.security import decode_access_token
from app.db.session import AsyncSession, get_db


async def get_current_user(
    authorization: Annotated[Optional[str], Header()] = None,
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedException("Authorization header missing or malformed")
    token = authorization.removeprefix("Bearer ")
    return decode_access_token(token)


# Convenience type aliases for endpoint injection
DatabaseDep = Annotated[AsyncSession, Depends(get_db)]
CacheDep = Annotated[NoopCache, Depends(get_noop_cache)]
CurrentUserDep = Annotated[dict, Depends(get_current_user)]

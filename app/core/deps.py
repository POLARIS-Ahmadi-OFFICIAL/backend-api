from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth import AuthUser, verify_supabase_jwt
from app.core.config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthUser:
    if settings.auth_disabled:
        return AuthUser(id="dev-user", email="dev@local")
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return verify_supabase_jwt(credentials.credentials, settings)

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import settings

bearer = HTTPBearer(auto_error=False)
TOKEN_TTL_HOURS = 12


def create_token() -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": "admin", "iat": now, "exp": now + timedelta(hours=TOKEN_TTL_HOURS)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def check_token(token: str) -> bool:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload.get("sub") == "admin"
    except Exception:
        return False


async def require_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    if creds is None or not check_token(creds.credentials):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
    return "admin"

from __future__ import annotations

from fastapi import Header, HTTPException


async def get_current_user(authorization: str = Header(default="")) -> str:
    """Extract user identity from Authorization header.

    For MVP, accepts any non-empty bearer token.
    Returns 'default' when no token is present.
    """
    if not authorization:
        return "default"

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization[7:]
    if not token.strip():
        raise HTTPException(status_code=401, detail="Empty token")

    return "authenticated-user"

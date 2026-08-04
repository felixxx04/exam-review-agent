from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.db.models import User
from app.services.auth_service import hash_password, normalize_username


async def create_admin(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    display_name: str,
) -> User:
    normalized = normalize_username(username)
    if not 10 <= len(password) <= 128:
        raise ValueError("Password must contain 10 to 128 characters")
    existing = await db.execute(select(User.id).where(User.username == normalized))
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"User {normalized!r} already exists")

    user = User(
        username=normalized,
        email=None,
        hashed_password=hash_password(password),
        display_name=display_name.strip()[:100] or normalized,
        role="admin",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _run(username: str, display_name: str) -> None:
    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    async with AsyncSessionLocal() as db:
        user = await create_admin(
            db,
            username=username,
            password=password,
            display_name=display_name,
        )
    print(f"Created administrator: {user.username}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local administrator")
    parser.add_argument("username")
    parser.add_argument("--display-name", default="Administrator")
    args = parser.parse_args()
    asyncio.run(_run(args.username, args.display_name))


if __name__ == "__main__":
    main()

"""Recover stale S3 material reservations for one tenant."""

from __future__ import annotations

import argparse
import asyncio
import datetime

from app.api.dependencies import get_object_storage
from app.db.database import AsyncSessionLocal
from app.services.material_storage_cleanup import (
    ReservationRecoveryReport,
    recover_stale_material_reservations_for_user,
)


async def recover_material_storage(
    *,
    user_id: int,
    older_than_minutes: int = 60,
) -> ReservationRecoveryReport:
    """Recover one user's stale reservations without exposing storage data."""
    if older_than_minutes <= 0:
        raise ValueError("older_than_minutes must be positive")
    older_than = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        minutes=older_than_minutes
    )
    async with AsyncSessionLocal() as db:
        return await recover_stale_material_reservations_for_user(
            db,
            get_object_storage(),
            user_id=user_id,
            older_than=older_than,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recover stale object-storage reservations for one user"
    )
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--older-than-minutes", type=int, default=60)
    args = parser.parse_args()
    try:
        report = asyncio.run(
            recover_material_storage(
                user_id=args.user_id,
                older_than_minutes=args.older_than_minutes,
            )
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        "Recovered material storage reservations: "
        f"scanned={report.scanned} "
        f"objects_cleaned={report.objects_cleaned} "
        f"tombstones_written={report.tombstones_written} "
        f"pending={report.pending}"
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.db.models import Course, Material
from app.services.account_deletion_service import (
    AccountArtifactCleaner,
    AccountDeletionService,
    MaterialArtifact,
)


@dataclass
class RecordingObjectStorage:
    deleted: list[tuple[str, str | None]]

    async def delete_object(self, *, key: str, version_id: str | None = None) -> None:
        self.deleted.append((key, version_id))


class RecordingVectorStore:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_collection(self, scope: str) -> None:
        self.deleted.append(scope)


@pytest.mark.asyncio
async def test_account_artifact_cleaner_uses_object_keys_not_local_paths() -> None:
    storage = RecordingObjectStorage(deleted=[])
    vectors = RecordingVectorStore()
    cleaner = AccountArtifactCleaner(storage, vectors)

    await cleaner.clean(
        user_id=12,
        course_ids=[34],
        materials=[
            MaterialArtifact(
                object_key="users/12/courses/34/materials/56/objects/random",
                object_version_id="version-1",
            )
        ],
    )

    assert storage.deleted == [
        ("users/12/courses/34/materials/56/objects/random", "version-1")
    ]
    assert vectors.deleted == ["12", "12_course_34"]


@pytest.mark.asyncio
async def test_account_deletion_removes_every_owned_object_before_cascading(
    db_session, authenticated_user
):
    course = Course(user_id=authenticated_user.id, name="Owned course", is_default=True)
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Material(
            user_id=authenticated_user.id,
            course_id=course.id,
            filename="opaque-name",
            original_filename="notes.pdf",
            file_type="pdf",
            file_size=1,
            object_key=(
                f"users/{authenticated_user.id}/courses/{course.id}/"
                "materials/99/objects/random"
            ),
            object_version_id="version-1",
            storage_status="available",
        )
    )
    await db_session.commit()

    storage = RecordingObjectStorage(deleted=[])
    service = AccountDeletionService(
        db_session,
        AccountArtifactCleaner(storage, RecordingVectorStore()),
    )
    result = await service.request(authenticated_user.id)
    await service.execute(result.job.public_id)

    assert result.job.status == "succeeded"
    assert storage.deleted == [
        (
            f"users/{authenticated_user.id}/courses/{course.id}/"
            "materials/99/objects/random",
            "version-1",
        )
    ]

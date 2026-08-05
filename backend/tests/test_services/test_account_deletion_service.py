from __future__ import annotations

import datetime

import pytest

from app.core.exceptions import AppException
from app.db.models import Course, InviteCode, Material, User
from app.services.quota_service import QuotaService


class RecordingVectorStore:
    def __init__(self, *, fail_once: bool = False) -> None:
        self.deleted: list[str] = []
        self.fail_once = fail_once

    def delete_collection(self, scope: str) -> None:
        self.deleted.append(scope)
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("vector backend unavailable")


async def _user_with_material(db_session, tmp_path, username: str):
    user = User(username=username, hashed_password="hash", display_name=username)
    db_session.add(user)
    await db_session.flush()
    course = Course(user_id=user.id, name="Deletion", is_default=True)
    db_session.add(course)
    await db_session.flush()
    filename = f"{username}.pdf"
    (tmp_path / filename).write_bytes(b"private material")
    material = Material(
        user_id=user.id,
        course_id=course.id,
        filename=filename,
        original_filename=filename,
        file_type="pdf",
        file_size=16,
    )
    db_session.add(material)
    await db_session.commit()
    return user, course, material


@pytest.mark.asyncio
async def test_account_deletion_removes_database_files_and_vector_scopes(
    db_session, tmp_path
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, course, material = await _user_with_material(
        db_session, tmp_path, "delete_success"
    )
    vector_store = RecordingVectorStore()
    cleaner = AccountArtifactCleaner(tmp_path, vector_store)

    result = await AccountDeletionService(db_session, cleaner).request(user.id)
    status = await AccountDeletionService(db_session, cleaner).get_status(
        result.job.public_id, result.status_token
    )

    assert result.job.status == "succeeded"
    assert status.status == "succeeded"
    assert status.user_id is None
    assert await db_session.get(User, user.id) is None
    assert not (tmp_path / material.filename).exists()
    assert vector_store.deleted == [
        str(user.id),
        f"{user.id}_course_{course.id}",
    ]


@pytest.mark.asyncio
async def test_failed_account_deletion_is_visible_retryable_and_idempotent(
    db_session, tmp_path
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, _, _ = await _user_with_material(db_session, tmp_path, "delete_retry")
    vector_store = RecordingVectorStore(fail_once=True)
    cleaner = AccountArtifactCleaner(tmp_path, vector_store)
    service = AccountDeletionService(db_session, cleaner)
    invite = InviteCode(
        code_hash="d" * 64,
        created_by_user_id=user.id,
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
    )
    db_session.add(invite)
    await db_session.commit()

    requested = await service.request(user.id)

    assert requested.job.status == "failed"
    assert requested.job.attempt_count == 1
    assert requested.job.error_code == "ARTIFACT_CLEANUP_FAILED"
    assert await db_session.get(User, user.id) is not None
    await db_session.refresh(user)
    await db_session.refresh(invite)
    assert user.is_disabled is True
    assert invite.disabled_at is not None
    with pytest.raises(AppException) as duplicate:
        await service.request(user.id)
    assert duplicate.value.code == "CONFLICT"
    with pytest.raises(AppException) as wrong_token:
        await service.get_status(requested.job.public_id, "wrong-token")
    assert wrong_token.value.code == "NOT_FOUND"

    retried = await service.retry(requested.job.public_id, requested.status_token)
    calls_after_success = list(vector_store.deleted)
    repeated = await service.retry(requested.job.public_id, requested.status_token)

    assert retried.status == "succeeded"
    assert retried.attempt_count == 2
    assert repeated.status == "succeeded"
    assert vector_store.deleted == calls_after_success
    assert await db_session.get(User, user.id) is None


@pytest.mark.asyncio
async def test_account_deletion_api_returns_queryable_status_token(client_with_db):
    response = await client_with_db.post("/api/account/deletion")

    assert response.status_code == 202
    created = response.json()["data"]
    assert created["status"] == "succeeded"
    assert created["status_token"]

    status = await client_with_db.get(
        f"/api/account/deletions/{created['job_id']}",
        headers={"X-Deletion-Status-Token": created["status_token"]},
    )
    rejected = await client_with_db.get(
        f"/api/account/deletions/{created['job_id']}",
        headers={"X-Deletion-Status-Token": "wrong-token"},
    )

    assert status.status_code == 200
    assert status.json()["data"]["status"] == "succeeded"
    assert "status_token" not in status.json()["data"]
    assert rejected.status_code == 404


@pytest.mark.asyncio
async def test_quota_service_allows_capacity_and_rejects_missing_users(
    db_session, authenticated_user
):
    usage = await QuotaService(db_session).ensure_upload_allowed(
        authenticated_user.id, 1024
    )

    assert usage.files_used == 0
    assert usage.storage_used_bytes == 0
    with pytest.raises(AppException) as missing:
        await QuotaService(db_session).ensure_upload_allowed(999_999, 1)
    assert missing.value.code == "NOT_FOUND"

    authenticated_user.is_disabled = True
    await db_session.commit()
    with pytest.raises(AppException) as frozen:
        await QuotaService(db_session).ensure_upload_allowed(authenticated_user.id, 1)
    assert frozen.value.code == "ACCOUNT_DELETION_IN_PROGRESS"


@pytest.mark.asyncio
async def test_account_artifact_cleaner_rejects_paths_outside_upload_root(tmp_path):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        MaterialArtifact,
    )

    outside = tmp_path.parent / f"{tmp_path.name}-outside.pdf"
    outside.write_bytes(b"must remain")
    vector_store = RecordingVectorStore()
    cleaner = AccountArtifactCleaner(tmp_path, vector_store)

    try:
        with pytest.raises(ValueError, match="outside the upload root"):
            await cleaner.clean(
                1,
                [],
                [MaterialArtifact(filename=outside.name, storage_path=str(outside))],
            )
        assert outside.exists()
        assert vector_store.deleted == []
    finally:
        outside.unlink(missing_ok=True)

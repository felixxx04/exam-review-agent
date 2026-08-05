from __future__ import annotations

import datetime

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AppException
from app.db.models import AccountDeletionJob, Course, InviteCode, Material, User
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

    service = AccountDeletionService(db_session, cleaner)
    result = await service.request(user.id)

    assert result.job.status == "pending"
    assert await db_session.get(User, user.id) is not None
    assert vector_store.deleted == []

    await service.execute(result.job.public_id)
    status = await service.get_status(
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

    assert requested.job.status == "pending"
    await service.execute(requested.job.public_id)

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
async def test_account_deletion_api_returns_queryable_status_token(
    client_with_db, monkeypatch
):
    from unittest.mock import AsyncMock

    execute_deletion = AsyncMock()
    monkeypatch.setattr("app.api.account._execute_deletion", execute_deletion)

    response = await client_with_db.post("/api/account/deletion")

    assert response.status_code == 202
    created = response.json()["data"]
    assert created["status"] == "pending"
    assert created["status_token"]
    execute_deletion.assert_awaited_once_with(created["job_id"])

    status = await client_with_db.get(
        f"/api/account/deletions/{created['job_id']}",
        headers={"X-Deletion-Status-Token": created["status_token"]},
    )
    rejected = await client_with_db.get(
        f"/api/account/deletions/{created['job_id']}",
        headers={"X-Deletion-Status-Token": "wrong-token"},
    )

    assert status.status_code == 200
    assert status.json()["data"]["status"] == "pending"
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


@pytest.mark.asyncio
async def test_request_returns_queryable_token_when_deletion_preparation_fails(
    db_session, tmp_path, monkeypatch
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, _, _ = await _user_with_material(
        db_session, tmp_path, "delete_prepare_failure"
    )
    original_execute = db_session.execute
    failed_once = False

    async def fail_course_snapshot(statement, *args, **kwargs):
        nonlocal failed_once
        if not failed_once and "FROM courses" in str(statement):
            failed_once = True
            raise RuntimeError("database snapshot unavailable")
        return await original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", fail_course_snapshot)
    service = AccountDeletionService(
        db_session,
        AccountArtifactCleaner(tmp_path, RecordingVectorStore()),
    )

    requested = await service.request(user.id)
    await service.execute(requested.job.public_id)
    status = await service.get_status(requested.job.public_id, requested.status_token)

    assert failed_once is True
    assert requested.status_token
    assert status.status == "failed"
    assert status.error_code == "DATABASE_DELETION_FAILED"
    assert status.attempt_count == 1


@pytest.mark.asyncio
async def test_committed_success_is_not_downgraded_when_commit_result_is_uncertain(
    db_session, tmp_path, monkeypatch
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, _, _ = await _user_with_material(
        db_session, tmp_path, "delete_commit_uncertain"
    )
    original_commit = db_session.commit
    raised_once = False

    async def commit_then_report_failure():
        nonlocal raised_once
        should_raise = not raised_once and any(
            isinstance(instance, AccountDeletionJob) and instance.status == "succeeded"
            for instance in db_session.identity_map.values()
        )
        await original_commit()
        if should_raise:
            raised_once = True
            raise RuntimeError("commit acknowledgement lost")

    monkeypatch.setattr(db_session, "commit", commit_then_report_failure)
    service = AccountDeletionService(
        db_session,
        AccountArtifactCleaner(tmp_path, RecordingVectorStore()),
    )

    requested = await service.request(user.id)
    await service.execute(requested.job.public_id)
    status = await service.get_status(requested.job.public_id, requested.status_token)

    assert raised_once is True
    assert status.status == "succeeded"
    assert status.user_id is None


@pytest.mark.asyncio
async def test_execution_recovery_failure_leaves_the_delivered_token_retryable(
    db_session, tmp_path, monkeypatch
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, _, _ = await _user_with_material(
        db_session, tmp_path, "delete_recovery_failure"
    )
    service = AccountDeletionService(
        db_session,
        AccountArtifactCleaner(tmp_path, RecordingVectorStore()),
    )
    requested = await service.request(user.id)
    original_commit = db_session.commit

    async def fail_final_commit():
        if any(
            isinstance(instance, AccountDeletionJob) and instance.status == "succeeded"
            for instance in db_session.identity_map.values()
        ):
            raise SQLAlchemyError("database deletion unavailable")
        await original_commit()

    async def fail_status_reload(_job_id):
        raise SQLAlchemyError("status recovery unavailable")

    monkeypatch.setattr(db_session, "commit", fail_final_commit)
    monkeypatch.setattr(service, "_reload_job", fail_status_reload)

    await service.execute(requested.job.public_id)
    status = await service.get_status(requested.job.public_id, requested.status_token)

    assert status.status == "pending"
    assert status.user_id == user.id

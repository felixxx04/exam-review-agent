from __future__ import annotations

import datetime

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AppException
from app.db.models import (
    AccountDeletionJob,
    Course,
    InviteCode,
    Material,
    MaterialJob,
    MaterialJobStatus,
    ProcessingStatus,
    StorageStatus,
    User,
)
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


async def _user_with_material(db_session, object_storage, username: str):
    user = User(username=username, hashed_password="hash", display_name=username)
    db_session.add(user)
    await db_session.flush()
    course = Course(user_id=user.id, name="Deletion", is_default=True)
    db_session.add(course)
    await db_session.flush()
    filename = f"{username}-object"
    material = Material(
        user_id=user.id,
        course_id=course.id,
        filename=filename,
        original_filename=filename,
        file_type="pdf",
        file_size=16,
        storage_status="available",
    )
    db_session.add(material)
    await db_session.flush()
    material.object_key = (
        f"users/{user.id}/courses/{course.id}/materials/{material.id}/"
        f"objects/{material.object_id}"
    )
    material.object_version_id = "in-memory-version"
    object_storage.objects[material.object_key] = b"private material"
    await db_session.commit()
    return user, course, material


@pytest.mark.asyncio
async def test_account_deletion_removes_database_files_and_vector_scopes(
    db_session, object_storage
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, course, material = await _user_with_material(
        db_session, object_storage, "delete_success"
    )
    vector_store = RecordingVectorStore()
    cleaner = AccountArtifactCleaner(object_storage, vector_store)

    service = AccountDeletionService(db_session, cleaner)
    result = await service.request(user.id)

    assert result.job.status == "pending"
    assert await db_session.get(User, user.id) is not None
    assert vector_store.deleted == []

    await service.execute(result.job.public_id)
    status = await service.get_status(result.job.public_id, result.status_token)

    assert result.job.status == "succeeded"
    assert status.status == "succeeded"
    assert status.user_id is None
    assert await db_session.get(User, user.id) is None
    assert material.object_key not in object_storage.objects
    assert vector_store.deleted == [
        str(user.id),
        f"{user.id}_course_{course.id}",
    ]


@pytest.mark.asyncio
async def test_account_deletion_fences_queued_and_running_material_jobs(
    db_session, object_storage
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, course, material = await _user_with_material(
        db_session, object_storage, "delete_with_material_job"
    )
    material.processing_status = ProcessingStatus.PROCESSING
    material.processing_lease_id = "live-worker-attempt"
    material.processing_lease_expires_at = datetime.datetime.now(
        datetime.UTC
    ) + datetime.timedelta(minutes=5)
    job = MaterialJob(
        user_id=user.id,
        course_id=course.id,
        material_id=material.id,
        status=MaterialJobStatus.RUNNING,
        attempt_count=1,
        idempotency_key="material:account-delete:process:0",
    )
    db_session.add(job)
    await db_session.commit()

    service = AccountDeletionService(
        db_session, AccountArtifactCleaner(object_storage, RecordingVectorStore())
    )
    requested = await service.request(user.id)
    await service.execute(requested.job.public_id)

    assert requested.job.status == "succeeded"
    assert await db_session.get(User, user.id) is None


@pytest.mark.asyncio
async def test_account_deletion_keeps_an_unknown_object_write_tombstone_retryable(
    db_session, object_storage
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, _course, material = await _user_with_material(
        db_session, object_storage, "delete_unknown_object_write"
    )
    material.storage_status = StorageStatus.DELETING
    material.object_write_uncertain = True
    await db_session.commit()
    vector_store = RecordingVectorStore()
    service = AccountDeletionService(
        db_session, AccountArtifactCleaner(object_storage, vector_store)
    )

    requested = await service.request(user.id)
    await service.execute(requested.job.public_id)

    assert requested.job.status == "failed"
    assert requested.job.error_code == "ARTIFACT_CLEANUP_FAILED"
    assert await db_session.get(User, user.id) is not None
    assert await db_session.get(Material, material.id) is not None
    assert material.object_key in object_storage.objects
    assert vector_store.deleted == []


@pytest.mark.asyncio
async def test_failed_account_deletion_is_visible_retryable_and_idempotent(
    db_session, object_storage
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, _, _ = await _user_with_material(db_session, object_storage, "delete_retry")
    vector_store = RecordingVectorStore(fail_once=True)
    cleaner = AccountArtifactCleaner(object_storage, vector_store)
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
async def test_account_deletion_retries_an_ordinary_deleting_material(
    db_session, object_storage
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, _course, material = await _user_with_material(
        db_session, object_storage, "delete_ordinary_deleting"
    )
    material.storage_status = StorageStatus.DELETING
    await db_session.commit()
    object_storage.fail_delete = True
    service = AccountDeletionService(
        db_session,
        AccountArtifactCleaner(object_storage, RecordingVectorStore()),
    )

    requested = await service.request(user.id)
    await service.execute(requested.job.public_id)

    assert requested.job.status == "failed"
    assert await db_session.get(Material, material.id) is not None

    object_storage.fail_delete = False
    retried = await service.retry(requested.job.public_id, requested.status_token)

    assert retried.status == "succeeded"
    assert await db_session.get(User, user.id) is None


@pytest.mark.asyncio
async def test_account_deletion_reclaims_an_expired_processing_material(
    db_session, object_storage
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, _course, material = await _user_with_material(
        db_session, object_storage, "delete_stale_processing"
    )
    material.processing_status = ProcessingStatus.PROCESSING
    material.processing_lease_expires_at = None
    await db_session.commit()
    service = AccountDeletionService(
        db_session,
        AccountArtifactCleaner(object_storage, RecordingVectorStore()),
    )

    requested = await service.request(user.id)
    await service.execute(requested.job.public_id)

    assert requested.job.status == "succeeded"
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
async def test_account_artifact_cleaner_removes_objects_before_vectors(object_storage):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        MaterialArtifact,
    )

    vector_store = RecordingVectorStore()
    object_key = "users/1/courses/2/materials/3/objects/object-id"
    object_storage.objects[object_key] = b"must be removed"
    cleaner = AccountArtifactCleaner(object_storage, vector_store)

    await cleaner.clean(
        1,
        [2],
        [MaterialArtifact(object_key=object_key, object_version_id="version-1")],
    )

    assert object_key not in object_storage.objects
    assert vector_store.deleted == ["1", "1_course_2"]


@pytest.mark.asyncio
async def test_account_deletion_cleans_legacy_local_materials_during_transition(
    db_session, object_storage, tmp_path
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user = User(username="legacy-delete", hashed_password="hash", display_name="Legacy")
    db_session.add(user)
    await db_session.flush()
    course = Course(user_id=user.id, name="Legacy", is_default=True)
    db_session.add(course)
    await db_session.flush()
    legacy_path = tmp_path / "legacy-delete.pdf"
    legacy_path.write_bytes(b"legacy private material")
    db_session.add(
        Material(
            user_id=user.id,
            course_id=course.id,
            filename=legacy_path.name,
            original_filename=legacy_path.name,
            file_type="pdf",
            file_size=legacy_path.stat().st_size,
            storage_backend="legacy_local",
            storage_status="available",
            storage_path=str(legacy_path),
        )
    )
    await db_session.commit()

    service = AccountDeletionService(
        db_session,
        AccountArtifactCleaner(
            object_storage,
            RecordingVectorStore(),
            legacy_upload_root=tmp_path,
        ),
    )
    result = await service.request(user.id)
    await service.execute(result.job.public_id)

    assert result.job.status == "succeeded"
    assert not legacy_path.exists()
    assert await db_session.get(User, user.id) is None


@pytest.mark.asyncio
async def test_request_returns_queryable_token_when_deletion_preparation_fails(
    db_session, object_storage, monkeypatch
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, _, _ = await _user_with_material(
        db_session, object_storage, "delete_prepare_failure"
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
        AccountArtifactCleaner(object_storage, RecordingVectorStore()),
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
    db_session, object_storage, monkeypatch
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, _, _ = await _user_with_material(
        db_session, object_storage, "delete_commit_uncertain"
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
        AccountArtifactCleaner(object_storage, RecordingVectorStore()),
    )

    requested = await service.request(user.id)
    await service.execute(requested.job.public_id)
    status = await service.get_status(requested.job.public_id, requested.status_token)

    assert raised_once is True
    assert status.status == "succeeded"
    assert status.user_id is None


@pytest.mark.asyncio
async def test_execution_recovery_failure_leaves_the_delivered_token_retryable(
    db_session, object_storage, monkeypatch
):
    from app.services.account_deletion_service import (
        AccountArtifactCleaner,
        AccountDeletionService,
    )

    user, _, _ = await _user_with_material(
        db_session, object_storage, "delete_recovery_failure"
    )
    service = AccountDeletionService(
        db_session,
        AccountArtifactCleaner(object_storage, RecordingVectorStore()),
    )
    requested = await service.request(user.id)
    job_id = requested.job.public_id
    user_id = user.id
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

    await service.execute(job_id)
    status = await service.get_status(job_id, requested.status_token)

    assert status.status == "pending"
    assert status.user_id == user_id

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import (
    Course,
    Material,
    MaterialJob,
    MaterialJobStatus,
    ProcessingStatus,
    StorageStatus,
)
from app.services.job_service import JobService, SAFE_PROCESSING_ERROR


MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"


class RecordingQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def enqueue_job(self, function_name: str, *args, **kwargs):
        self.calls.append((function_name, args, kwargs))
        return SimpleNamespace(job_id=kwargs.get("_job_id"))


def test_worker_registers_a_periodic_material_job_recovery_cron():
    from app.tasks.worker import WorkerSettings

    assert any(
        getattr(job, "name", "") == "recover_material_jobs"
        for job in WorkerSettings.cron_jobs
    )


async def _material(db_session, authenticated_user) -> Material:
    course = Course(
        user_id=authenticated_user.id,
        name="Task 2.2 follow-up",
        is_default=True,
    )
    db_session.add(course)
    await db_session.flush()
    material = Material(
        user_id=authenticated_user.id,
        course_id=course.id,
        filename="stored-object",
        original_filename="notes.pdf",
        file_type="pdf",
        file_size=10,
        storage_backend="s3",
        storage_status="available",
        object_key="users/1/courses/1/materials/1/objects/object",
        processing_status="pending",
    )
    db_session.add(material)
    await db_session.commit()
    await db_session.refresh(material)
    return material


@pytest.mark.asyncio
async def test_claim_does_not_run_a_job_that_exhausted_attempts(
    db_session, authenticated_user
):
    material = await _material(db_session, authenticated_user)
    job = MaterialJob(
        user_id=authenticated_user.id,
        course_id=material.course_id,
        material_id=material.id,
        status=MaterialJobStatus.QUEUED,
        attempt_count=3,
        max_attempts=3,
        idempotency_key="material:exhausted:process:0",
    )
    db_session.add(job)
    await db_session.commit()

    claimed = await JobService(db_session).claim_job(
        user_id=authenticated_user.id,
        job_id=job.public_id,
    )

    assert claimed is None
    await db_session.refresh(job)
    assert job.status == MaterialJobStatus.FAILED
    assert job.error_code == "MAX_ATTEMPTS_EXCEEDED"
    assert job.error_message == SAFE_PROCESSING_ERROR


@pytest.mark.asyncio
async def test_failed_job_is_requeued_and_delivered_when_attempts_remain(
    db_session, authenticated_user
):
    material = await _material(db_session, authenticated_user)
    job = MaterialJob(
        user_id=authenticated_user.id,
        course_id=material.course_id,
        material_id=material.id,
        status=MaterialJobStatus.RUNNING,
        attempt_count=1,
        max_attempts=3,
        idempotency_key="material:retry-delivery:process:0",
    )
    db_session.add(job)
    await db_session.commit()
    queue = RecordingQueue()

    result = await JobService(db_session, queue=queue).mark_failed(
        user_id=authenticated_user.id,
        job_id=job.public_id,
    )

    assert result is not None
    await db_session.refresh(job)
    assert job.status == MaterialJobStatus.QUEUED
    available_at = job.available_at
    if available_at.tzinfo is None:
        available_at = available_at.replace(tzinfo=datetime.UTC)
    assert available_at >= datetime.datetime.now(datetime.UTC)
    assert queue.calls[0][0] == "process_material_job"
    assert queue.calls[0][1] == (job.public_id, authenticated_user.id)


@pytest.mark.asyncio
async def test_recovery_fences_stale_material_processing_attempt(
    db_session, authenticated_user
):
    material = await _material(db_session, authenticated_user)
    material.processing_status = ProcessingStatus.PROCESSING
    material.processing_lease_id = "stale-worker-lease"
    material.processing_lease_expires_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        minutes=10
    )
    db_session.add(
        MaterialJob(
            user_id=authenticated_user.id,
            course_id=material.course_id,
            material_id=material.id,
            status=MaterialJobStatus.RUNNING,
            attempt_count=1,
            max_attempts=3,
            started_at=datetime.datetime.now(datetime.UTC)
            - datetime.timedelta(minutes=10),
            updated_at=datetime.datetime.now(datetime.UTC)
            - datetime.timedelta(minutes=10),
            idempotency_key="material:stale-fence:process:0",
        )
    )
    await db_session.commit()

    queue = RecordingQueue()
    recovered = await JobService(db_session, queue=queue).recover_jobs(
        older_than=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1),
        user_id=authenticated_user.id,
    )

    assert recovered == 1
    await db_session.refresh(material)
    assert material.processing_status == ProcessingStatus.PENDING
    assert material.processing_lease_id is None
    assert material.processing_lease_expires_at is None


@pytest.mark.asyncio
async def test_cancel_material_job_does_not_overwrite_a_terminal_job(
    db_session, authenticated_user, monkeypatch
):
    material = await _material(db_session, authenticated_user)
    job = MaterialJob(
        user_id=authenticated_user.id,
        course_id=material.course_id,
        material_id=material.id,
        status=MaterialJobStatus.SUCCEEDED,
        idempotency_key="material:cancel-race:process:0",
    )
    db_session.add(job)
    await db_session.commit()
    stale_view = MaterialJob(
        user_id=authenticated_user.id,
        course_id=material.course_id,
        material_id=material.id,
        public_id=job.public_id,
        status=MaterialJobStatus.RUNNING,
        idempotency_key="material:cancel-race:stale-view",
    )
    service = JobService(db_session)
    monkeypatch.setattr(
        service,
        "get_material_job",
        AsyncMock(return_value=stale_view),
    )

    result = await service.cancel_material_job(
        user_id=authenticated_user.id,
        material_id=material.id,
    )

    assert result.status == MaterialJobStatus.SUCCEEDED
    await db_session.refresh(job)
    await db_session.refresh(material)
    assert job.status == MaterialJobStatus.SUCCEEDED
    assert material.processing_status == ProcessingStatus.PENDING


@pytest.mark.asyncio
async def test_retry_job_rejects_deleted_material(
    db_session, authenticated_user
):
    material = await _material(db_session, authenticated_user)
    material.storage_status = StorageStatus.DELETED
    job = MaterialJob(
        user_id=authenticated_user.id,
        course_id=material.course_id,
        material_id=material.id,
        status=MaterialJobStatus.FAILED,
        idempotency_key="material:deleted-retry:process:0",
    )
    db_session.add(job)
    await db_session.commit()

    with pytest.raises(LookupError):
        await JobService(db_session).retry_material_job(
            user_id=authenticated_user.id,
            material_id=material.id,
        )


@pytest.mark.asyncio
async def test_reprocess_job_creation_failure_does_not_leave_orphaned_pending_material(
    client_with_db, db_session, monkeypatch
):
    response = await client_with_db.post(
        "/api/materials",
        files={"file": ("reprocess-failure.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert response.status_code == 200
    material_id = response.json()["data"]["id"]
    material = await db_session.get(Material, material_id)
    assert material is not None
    material.processing_status = ProcessingStatus.FAILED
    await db_session.commit()

    async def fail_create(self, **kwargs):
        raise RuntimeError("job persistence unavailable")

    monkeypatch.setattr(JobService, "create_material_job", fail_create)
    with pytest.raises(RuntimeError, match="job persistence"):
        await client_with_db.post(f"/api/materials/{material_id}/reprocess")

    await db_session.refresh(material)
    assert material.processing_status == ProcessingStatus.FAILED
    jobs = list(
        (
            await db_session.scalars(
                select(MaterialJob).where(MaterialJob.material_id == material_id)
            )
        ).all()
    )
    assert all(job.status not in {MaterialJobStatus.QUEUED, MaterialJobStatus.RUNNING} for job in jobs)


@pytest.mark.asyncio
async def test_cancel_jobs_can_leave_the_callers_user_lock_open(
    db_session, authenticated_user
):
    material = await _material(db_session, authenticated_user)
    job = MaterialJob(
        user_id=authenticated_user.id,
        course_id=material.course_id,
        material_id=material.id,
        status=MaterialJobStatus.QUEUED,
        idempotency_key="material:lock-window:process:0",
    )
    db_session.add(job)
    await db_session.commit()

    cancelled = await JobService(db_session).cancel_jobs_for_material(
        user_id=authenticated_user.id,
        material_id=material.id,
        commit=False,
    )

    assert cancelled == 1
    assert db_session.in_transaction()
    assert job.status == MaterialJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_upload_job_persistence_failure_compensates_the_available_object(
    client_with_db, db_session, object_storage, monkeypatch
):
    async def fail_create(self, **kwargs):
        raise SQLAlchemyError("job persistence unavailable")

    monkeypatch.setattr(JobService, "create_material_job", fail_create)

    with pytest.raises(SQLAlchemyError, match="job persistence"):
        await client_with_db.post(
            "/api/materials",
            files={"file": ("job-failure.pdf", b"%PDF-1.4\n", "application/pdf")},
        )

    assert await db_session.scalar(select(Material)) is None
    assert object_storage.objects == {}


@pytest.mark.asyncio
async def test_recovery_cron_also_runs_material_storage_recovery(
    db_session, authenticated_user, object_storage, monkeypatch
):
    from app.tasks.parse_material import recover_material_jobs

    recover_storage = AsyncMock()
    monkeypatch.setattr(
        "app.tasks.parse_material.recover_stale_material_reservations_for_user",
        recover_storage,
    )

    await recover_material_jobs(
        {"db_session": db_session, "object_storage": object_storage}
    )

    recover_storage.assert_awaited_once()
    assert recover_storage.await_args.kwargs["user_id"] == authenticated_user.id


@pytest.mark.asyncio
async def test_admin_cannot_retry_cancelled_material_job(
    client_with_db, db_session, authenticated_user
):
    material = await _material(db_session, authenticated_user)
    job = MaterialJob(
        user_id=authenticated_user.id,
        course_id=material.course_id,
        material_id=material.id,
        status=MaterialJobStatus.CANCELLED,
        idempotency_key="material:admin-cancelled:process:0",
    )
    db_session.add(job)
    authenticated_user.role = "admin"
    await db_session.commit()

    response = await client_with_db.post(
        f"/api/admin/material-jobs/{job.public_id}/retry"
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_deleting_material_cancels_queued_job(
    client_with_db, db_session, authenticated_user, object_storage
):
    material = await _material(db_session, authenticated_user)
    job = MaterialJob(
        user_id=authenticated_user.id,
        course_id=material.course_id,
        material_id=material.id,
        status=MaterialJobStatus.QUEUED,
        idempotency_key="material:delete-cancel:process:0",
    )
    db_session.add(job)
    await db_session.commit()

    response = await client_with_db.delete(f"/api/materials/{material.id}")

    assert response.status_code == 200
    await db_session.refresh(job)
    assert job.status == MaterialJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_admin_job_api_lists_prioritizes_and_retries_without_storage_details(
    client_with_db, db_session, authenticated_user
):
    material = await _material(db_session, authenticated_user)
    job = MaterialJob(
        user_id=authenticated_user.id,
        course_id=material.course_id,
        material_id=material.id,
        status=MaterialJobStatus.FAILED,
        error_code="PROCESSING_FAILED",
        error_message="Material processing failed",
        idempotency_key="material:admin-api:process:0",
    )
    db_session.add(job)
    authenticated_user.role = "admin"
    await db_session.commit()

    listed = await client_with_db.get("/api/admin/material-jobs")

    assert listed.status_code == 200
    body = listed.json()["data"][0]
    assert body["public_id"] == job.public_id
    assert "object_key" not in body
    assert "signed_url" not in body

    prioritized = await client_with_db.patch(
        f"/api/admin/material-jobs/{job.public_id}/priority",
        json={"priority": 10},
    )
    assert prioritized.status_code == 200
    assert prioritized.json()["data"]["priority"] == 10

    retried = await client_with_db.post(
        f"/api/admin/material-jobs/{job.public_id}/retry"
    )
    assert retried.status_code == 200
    assert retried.json()["data"]["status"] == MaterialJobStatus.QUEUED.value


@pytest.mark.asyncio
async def test_regular_user_cannot_access_admin_job_api(
    client_with_db, db_session, authenticated_user
):
    response = await client_with_db.get("/api/admin/material-jobs")

    assert response.status_code == 403

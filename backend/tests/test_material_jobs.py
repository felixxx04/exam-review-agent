from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.models import Course, Material, MaterialJob, MaterialJobStatus, User
from app.services.job_service import JobService


class RecordingQueue:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.error = error

    async def enqueue_job(self, function_name: str, *args, **kwargs):
        self.calls.append((function_name, args, kwargs))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(job_id=kwargs.get("_job_id"))


async def _material(db_session, authenticated_user) -> Material:
    course = Course(
        user_id=authenticated_user.id,
        name="Async jobs",
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
async def test_create_material_job_is_idempotent_and_enqueues_once(
    db_session, authenticated_user
):
    material = await _material(db_session, authenticated_user)
    queue = RecordingQueue()
    service = JobService(db_session, queue=queue)

    first = await service.create_material_job(
        user_id=authenticated_user.id,
        material_id=material.id,
        course_id=material.course_id,
    )
    second = await service.create_material_job(
        user_id=authenticated_user.id,
        material_id=material.id,
        course_id=material.course_id,
    )

    assert first.id == second.id
    assert first.status == MaterialJobStatus.QUEUED
    assert first.idempotency_key == f"material:{material.id}:process:0"
    assert len(queue.calls) == 1
    assert queue.calls[0][0] == "process_material_job"
    assert queue.calls[0][1] == (first.public_id, authenticated_user.id)
    assert queue.calls[0][2]["_job_id"] == first.public_id


@pytest.mark.asyncio
async def test_enqueue_failure_leaves_postgres_job_queued_for_recovery(
    db_session, authenticated_user
):
    material = await _material(db_session, authenticated_user)
    service = JobService(
        db_session,
        queue=RecordingQueue(error=ConnectionError("redis credentials leaked")),
    )

    job = await service.create_material_job(
        user_id=authenticated_user.id,
        material_id=material.id,
        course_id=material.course_id,
    )

    await db_session.refresh(job)
    assert job.status == MaterialJobStatus.QUEUED
    assert job.error_code is None
    assert job.error_message is None


@pytest.mark.asyncio
async def test_cancel_queued_job_is_idempotent_and_sets_material_failure(
    db_session, authenticated_user
):
    material = await _material(db_session, authenticated_user)
    queue = RecordingQueue()
    service = JobService(db_session, queue=queue)
    job = await service.create_material_job(
        user_id=authenticated_user.id,
        material_id=material.id,
        course_id=material.course_id,
    )

    cancelled = await service.cancel_material_job(
        user_id=authenticated_user.id,
        material_id=material.id,
    )
    repeated = await service.cancel_material_job(
        user_id=authenticated_user.id,
        material_id=material.id,
    )

    assert cancelled.id == job.id
    assert repeated.status == MaterialJobStatus.CANCELLED
    await db_session.refresh(material)
    assert material.processing_status == "failed"
    assert material.error_message == "Material processing cancelled"


@pytest.mark.asyncio
async def test_retry_failed_job_uses_exponential_backoff_and_clears_safe_error(
    db_session, authenticated_user
):
    material = await _material(db_session, authenticated_user)
    queue = RecordingQueue()
    service = JobService(db_session, queue=queue)
    job = MaterialJob(
        user_id=authenticated_user.id,
        course_id=material.course_id,
        material_id=material.id,
        status=MaterialJobStatus.FAILED,
        attempt_count=2,
        max_attempts=3,
        error_code="PROCESSING_FAILED",
        error_message="safe failure",
        idempotency_key="material:retry:process:0",
    )
    db_session.add(job)
    await db_session.commit()

    before = datetime.datetime.now(datetime.UTC)
    retried = await service.retry_material_job(
        user_id=authenticated_user.id,
        material_id=material.id,
    )

    assert retried.status == MaterialJobStatus.QUEUED
    assert retried.error_code is None
    assert retried.error_message is None
    assert retried.available_at is not None
    assert retried.available_at >= before + datetime.timedelta(seconds=4)
    assert len(queue.calls) == 1


@pytest.mark.asyncio
async def test_recovery_scanner_requeues_stale_running_and_missing_enqueue_jobs(
    db_session, authenticated_user
):
    material = await _material(db_session, authenticated_user)
    stale = MaterialJob(
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
        idempotency_key="material:stale:process:0",
    )
    db_session.add(stale)
    await db_session.commit()

    queue = RecordingQueue()
    service = JobService(db_session, queue=queue)
    recovered = await service.recover_jobs(
        older_than=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1)
    )

    assert recovered == 1
    await db_session.refresh(stale)
    assert stale.status == MaterialJobStatus.QUEUED
    assert stale.available_at is not None
    assert len(queue.calls) == 1


@pytest.mark.asyncio
async def test_job_queries_are_scoped_to_the_authenticated_user(
    db_session, authenticated_user
):
    material = await _material(db_session, authenticated_user)
    other = User(
        username="other-job-owner",
        email=None,
        hashed_password="hash",
        display_name="Other",
    )
    db_session.add(other)
    await db_session.flush()
    other_course = Course(user_id=other.id, name="Other course", is_default=True)
    db_session.add(other_course)
    await db_session.flush()
    db_session.add(
        MaterialJob(
            user_id=other.id,
            course_id=other_course.id,
            material_id=material.id,
            status=MaterialJobStatus.QUEUED,
            idempotency_key="material:other:process:0",
        )
    )
    await db_session.commit()

    service = JobService(db_session, queue=RecordingQueue())
    with pytest.raises(LookupError):
        await service.get_material_job(
            user_id=authenticated_user.id,
            material_id=material.id,
        )

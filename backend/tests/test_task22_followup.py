from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.models import Course, Material, MaterialJob, MaterialJobStatus
from app.services.job_service import JobService, SAFE_PROCESSING_ERROR


class RecordingQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def enqueue_job(self, function_name: str, *args, **kwargs):
        self.calls.append((function_name, args, kwargs))
        return SimpleNamespace(job_id=kwargs.get("_job_id"))


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
    assert job.available_at >= datetime.datetime.now(datetime.UTC)
    assert queue.calls[0][0] == "process_material_job"
    assert queue.calls[0][1] == (job.public_id, authenticated_user.id)


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

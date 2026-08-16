import json
from pathlib import Path

import yaml

from app.core.config import Settings
from app.db.database import _engine_kwargs, to_sync_database_url


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_postgresql_is_the_application_default():
    default_url = Settings.model_fields["database_url"].default

    assert default_url == (
        "postgresql+asyncpg://exam_review:exam-review-dev@localhost:5432/exam_review"
    )


def test_alembic_uses_psycopg_for_async_postgresql_url():
    assert (
        to_sync_database_url("postgresql+asyncpg://user:pass@localhost/exam_review")
        == "postgresql+psycopg://user:pass@localhost/exam_review"
    )


def test_alembic_uses_pysqlite_for_async_sqlite_url():
    assert to_sync_database_url("sqlite+aiosqlite:///./dev.db") == (
        "sqlite+pysqlite:///./dev.db"
    )


def test_sqlite_engine_waits_for_busy_database():
    kwargs = _engine_kwargs("sqlite+aiosqlite:///./dev.db")

    assert kwargs["connect_args"]["timeout"] >= 30


def test_non_sqlite_engine_uses_default_kwargs():
    assert _engine_kwargs("postgresql+asyncpg://user:pass@localhost/db") == {}


def test_compose_bootstraps_application_role_without_rls_bypass():
    compose = yaml.safe_load(
        (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    )
    postgres = compose["services"]["postgres"]

    assert postgres["environment"]["POSTGRES_USER"] == (
        "${POSTGRES_ADMIN_USER:-exam_review_admin}"
    )
    assert "./infra/postgres/init:/docker-entrypoint-initdb.d:ro" in postgres["volumes"]

    bootstrap = (
        REPOSITORY_ROOT / "infra" / "postgres" / "init" / "001-app-role.sh"
    ).read_text(encoding="utf-8")
    assert "CREATE ROLE exam_review" in bootstrap
    assert "NOSUPERUSER" in bootstrap
    assert "NOBYPASSRLS" in bootstrap


def test_compose_runs_minio_initialization_through_a_shell_entrypoint():
    compose = yaml.safe_load(
        (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    )
    minio_init = compose["services"]["minio-init"]

    assert minio_init["entrypoint"] == ["/bin/sh"]
    assert minio_init["command"][0] == "-ec"


def test_compose_minio_initialization_does_not_require_sed():
    compose = yaml.safe_load(
        (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    )
    script = compose["services"]["minio-init"]["command"][1]

    assert "sed " not in script
    assert "policy_template=$$(cat /policy/object-storage-policy.json)" in script
    assert "policy_template/__S3_BUCKET__" in script


def test_minio_policy_only_allows_version_listing_for_material_object_prefixes():
    policy = json.loads(
        (REPOSITORY_ROOT / "infra" / "minio" / "object-storage-policy.json").read_text(
            encoding="utf-8"
        )
    )
    statements = policy["Statement"]
    all_actions = {action for statement in statements for action in statement["Action"]}

    assert "s3:ListBucket" not in all_actions
    version_listing = next(
        statement
        for statement in statements
        if "s3:ListBucketVersions" in statement["Action"]
    )
    assert version_listing["Resource"] == ["arn:aws:s3:::__S3_BUCKET__"]
    assert version_listing["Condition"] == {
        "StringLike": {
            "s3:prefix": "users/*/courses/*/materials/*/objects/*",
        }
    }


def test_compose_minio_initialization_refreshes_an_existing_policy():
    compose = yaml.safe_load(
        (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    )
    script = compose["services"]["minio-init"]["command"][1]

    assert "if ! mc admin policy info" not in script
    assert (
        "mc admin policy create local exam-review-object-storage "
        "/tmp/object-storage-policy.json"
    ) in script

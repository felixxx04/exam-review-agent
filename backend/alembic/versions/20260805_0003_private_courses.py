"""Add private courses and bind study resources to a course.

Revision ID: 20260805_0003
Revises: 20260804_0002
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_0003"
down_revision = "20260804_0002"
branch_labels = None
depends_on = None


COURSE_OWNED_TABLES = (
    "conversations",
    "learning_profiles",
    "materials",
    "quiz_sessions",
    "answer_records",
    "mistake_records",
)

NEW_TENANT_TABLES = (
    "courses",
    "exams",
    "study_availabilities",
    "concepts",
    "concept_dependencies",
    "concept_masteries",
    "conversation_messages",
    "material_chunks",
    "questions",
)


def _enable_tenant_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{table}_tenant_isolation" ON "{table}" '
        "USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer) "
        "WITH CHECK (user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer)"
    )


def _disable_tenant_rls(table: str) -> None:
    op.execute(f'DROP POLICY IF EXISTS "{table}_tenant_isolation" ON "{table}"')
    op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


def _assert_legacy_concepts_empty() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM concepts)
               OR EXISTS (SELECT 1 FROM concept_dependencies) THEN
                RAISE EXCEPTION
                    'Cannot migrate non-empty legacy concepts into private courses';
            END IF;
        END $$;
        """
    )


def _collapse_learning_profiles_for_legacy_schema() -> None:
    op.execute(
        """
        DELETE FROM learning_profiles AS duplicate
        USING (
            SELECT lp.id,
                   ROW_NUMBER() OVER (
                       PARTITION BY lp.user_id
                       ORDER BY c.is_default DESC, c.created_at ASC, lp.id ASC
                   ) AS profile_rank
            FROM learning_profiles AS lp
            JOIN courses AS c ON c.id = lp.course_id
        ) AS ranked
        WHERE duplicate.id = ranked.id
          AND ranked.profile_rank > 1
        """
    )


def _delete_private_concepts_for_legacy_schema() -> None:
    op.execute("DELETE FROM concept_dependencies")
    op.execute("DELETE FROM concepts")


def upgrade() -> None:
    # Migrations run during maintenance; temporarily bypass existing RLS so
    # every tenant row can receive its owner's default course.
    for table in COURSE_OWNED_TABLES:
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_default", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_courses_name_not_blank"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_courses_id_user"),
        sa.UniqueConstraint("user_id", "name", name="uq_courses_user_name"),
    )
    op.create_index("ix_courses_user_id", "courses", ["user_id"])
    op.create_index("ix_courses_user_updated", "courses", ["user_id", "updated_at"])
    op.create_index(
        "uq_courses_one_default_per_user",
        "courses",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.execute(
        "INSERT INTO courses "
        "(user_id, name, description, is_default, created_at, updated_at) "
        "SELECT id, '默认课程', NULL, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
        "FROM users"
    )

    op.create_table(
        "exams",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("exam_date", sa.Date(), nullable=True),
        sa.Column("long_term_goal", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_exams_course_owner",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "course_id", name="uq_exams_user_course"),
    )
    op.create_index("ix_exams_user_id", "exams", ["user_id"])
    op.create_index("ix_exams_course_id", "exams", ["course_id"])
    op.execute(
        "INSERT INTO exams "
        "(user_id, course_id, exam_date, long_term_goal, created_at, updated_at) "
        "SELECT user_id, id, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
        "FROM courses"
    )

    op.create_table(
        "study_availabilities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column(
            "daily_available_minutes",
            sa.Integer(),
            server_default="60",
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "daily_available_minutes > 0 AND daily_available_minutes <= 1440",
            name="ck_study_availability_daily_minutes",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_study_availability_course_owner",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "course_id", name="uq_study_availability_user_course"
        ),
    )
    op.create_index(
        "ix_study_availabilities_user_id", "study_availabilities", ["user_id"]
    )
    op.create_index(
        "ix_study_availabilities_course_id", "study_availabilities", ["course_id"]
    )
    op.create_index(
        "ix_study_availability_user_course",
        "study_availabilities",
        ["user_id", "course_id"],
    )
    op.execute(
        "INSERT INTO study_availabilities "
        "(user_id, course_id, daily_available_minutes, updated_at) "
        "SELECT user_id, id, 60, CURRENT_TIMESTAMP FROM courses"
    )

    for table in COURSE_OWNED_TABLES:
        op.add_column(table, sa.Column("course_id", sa.Integer(), nullable=True))
        op.execute(
            f'UPDATE "{table}" AS target SET course_id = course.id '
            "FROM courses AS course "
            "WHERE course.user_id = target.user_id AND course.is_default = true"
        )
        op.alter_column(table, "course_id", nullable=False)
        op.create_index(f"ix_{table}_course_id", table, ["course_id"])
        op.create_foreign_key(
            f"fk_{table}_course_owner",
            table,
            "courses",
            ["course_id", "user_id"],
            ["id", "user_id"],
            ondelete="CASCADE",
        )

    _assert_legacy_concepts_empty()

    child_scope = {
        "conversation_messages": ("conversations", "conversation_id"),
        "material_chunks": ("materials", "material_id"),
        "questions": ("quiz_sessions", "quiz_session_id"),
    }
    for table, (parent_table, parent_id) in child_scope.items():
        op.add_column(table, sa.Column("user_id", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("course_id", sa.Integer(), nullable=True))
        op.execute(
            f'UPDATE "{table}" AS target '
            f"SET user_id = parent.user_id, course_id = parent.course_id "
            f'FROM "{parent_table}" AS parent '
            f"WHERE parent.id = target.{parent_id}"
        )
        op.alter_column(table, "user_id", nullable=False)
        op.alter_column(table, "course_id", nullable=False)
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
        op.create_index(f"ix_{table}_course_id", table, ["course_id"])
        op.create_index(f"ix_{table}_user_course", table, ["user_id", "course_id"])

    op.create_unique_constraint(
        "uq_conversations_scope", "conversations", ["id", "user_id", "course_id"]
    )
    op.create_unique_constraint(
        "uq_materials_scope", "materials", ["id", "user_id", "course_id"]
    )
    op.create_unique_constraint(
        "uq_quiz_sessions_scope", "quiz_sessions", ["id", "user_id", "course_id"]
    )
    op.create_unique_constraint(
        "uq_questions_scope", "questions", ["id", "user_id", "course_id"]
    )
    op.drop_constraint(
        "conversation_messages_conversation_id_fkey",
        "conversation_messages",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_conversation_messages_conversation_scope",
        "conversation_messages",
        "conversations",
        ["conversation_id", "user_id", "course_id"],
        ["id", "user_id", "course_id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "material_chunks_material_id_fkey", "material_chunks", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_material_chunks_material_scope",
        "material_chunks",
        "materials",
        ["material_id", "user_id", "course_id"],
        ["id", "user_id", "course_id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "questions_quiz_session_id_fkey", "questions", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_questions_quiz_scope",
        "questions",
        "quiz_sessions",
        ["quiz_session_id", "user_id", "course_id"],
        ["id", "user_id", "course_id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "answer_records_question_id_fkey", "answer_records", type_="foreignkey"
    )
    op.drop_constraint(
        "answer_records_quiz_session_id_fkey", "answer_records", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_answer_records_question_scope",
        "answer_records",
        "questions",
        ["question_id", "user_id", "course_id"],
        ["id", "user_id", "course_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_answer_records_quiz_scope",
        "answer_records",
        "quiz_sessions",
        ["quiz_session_id", "user_id", "course_id"],
        ["id", "user_id", "course_id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "mistake_records_question_id_fkey", "mistake_records", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_mistake_records_question_scope",
        "mistake_records",
        "questions",
        ["question_id", "user_id", "course_id"],
        ["id", "user_id", "course_id"],
        ondelete="CASCADE",
    )

    op.add_column(
        "conversations",
        sa.Column("available_minutes_override", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_conversations_available_minutes_override",
        "conversations",
        "available_minutes_override IS NULL OR "
        "(available_minutes_override > 0 AND available_minutes_override <= 1440)",
    )
    op.create_index(
        "ix_conversations_user_course_updated",
        "conversations",
        ["user_id", "course_id", "updated_at"],
    )

    op.drop_index("ix_learning_profiles_user_id", table_name="learning_profiles")
    op.create_index("ix_learning_profiles_user_id", "learning_profiles", ["user_id"])
    op.create_unique_constraint(
        "uq_learning_profiles_user_course",
        "learning_profiles",
        ["user_id", "course_id"],
    )
    op.create_index(
        "ix_materials_user_course_status",
        "materials",
        ["user_id", "course_id", "processing_status"],
    )
    op.create_index(
        "ix_quiz_sessions_user_course",
        "quiz_sessions",
        ["user_id", "course_id"],
    )
    op.create_index(
        "ix_answer_records_user_course",
        "answer_records",
        ["user_id", "course_id"],
    )
    op.create_index(
        "ix_mistakes_user_course_review",
        "mistake_records",
        ["user_id", "course_id", "next_review_at"],
    )

    # Concepts were global placeholders; non-empty legacy data is rejected above.
    op.add_column("concepts", sa.Column("user_id", sa.Integer(), nullable=True))
    op.add_column("concepts", sa.Column("course_id", sa.Integer(), nullable=True))
    op.alter_column("concepts", "user_id", nullable=False)
    op.alter_column("concepts", "course_id", nullable=False)
    op.create_index("ix_concepts_user_id", "concepts", ["user_id"])
    op.create_index("ix_concepts_course_id", "concepts", ["course_id"])
    op.create_foreign_key(
        "fk_concepts_user", "concepts", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_concepts_course_owner",
        "concepts",
        "courses",
        ["course_id", "user_id"],
        ["id", "user_id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_concepts_scope", "concepts", ["id", "user_id", "course_id"]
    )
    op.create_unique_constraint(
        "uq_concepts_course_name", "concepts", ["user_id", "course_id", "name"]
    )
    op.create_index(
        "ix_concepts_user_course_topic",
        "concepts",
        ["user_id", "course_id", "topic"],
    )

    op.add_column(
        "concept_dependencies", sa.Column("user_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "concept_dependencies", sa.Column("course_id", sa.Integer(), nullable=True)
    )
    op.alter_column("concept_dependencies", "user_id", nullable=False)
    op.alter_column("concept_dependencies", "course_id", nullable=False)
    op.create_index(
        "ix_concept_dependencies_user_id", "concept_dependencies", ["user_id"]
    )
    op.create_index(
        "ix_concept_dependencies_course_id", "concept_dependencies", ["course_id"]
    )
    op.create_index(
        "ix_concept_dependencies_user_course",
        "concept_dependencies",
        ["user_id", "course_id"],
    )
    op.create_foreign_key(
        "fk_concept_dependencies_user",
        "concept_dependencies",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "concept_dependencies_prerequisite_id_fkey",
        "concept_dependencies",
        type_="foreignkey",
    )
    op.drop_constraint(
        "concept_dependencies_dependent_id_fkey",
        "concept_dependencies",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_concept_dependencies_prerequisite_scope",
        "concept_dependencies",
        "concepts",
        ["prerequisite_id", "user_id", "course_id"],
        ["id", "user_id", "course_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_concept_dependencies_dependent_scope",
        "concept_dependencies",
        "concepts",
        ["dependent_id", "user_id", "course_id"],
        ["id", "user_id", "course_id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_concept_dependencies_distinct_nodes",
        "concept_dependencies",
        "prerequisite_id <> dependent_id",
    )

    op.create_table(
        "concept_masteries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("concept_id", sa.Integer(), nullable=False),
        sa.Column("mastery_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("evidence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mastery_score >= 0 AND mastery_score <= 1",
            name="ck_concept_mastery_score",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_concept_mastery_course_owner",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id", "user_id", "course_id"],
            ["concepts.id", "concepts.user_id", "concepts.course_id"],
            ondelete="CASCADE",
            name="fk_concept_mastery_concept_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "course_id", "concept_id", name="uq_concept_mastery_scope"
        ),
    )
    op.create_index("ix_concept_masteries_user_id", "concept_masteries", ["user_id"])
    op.create_index(
        "ix_concept_masteries_course_id", "concept_masteries", ["course_id"]
    )
    op.create_index(
        "ix_concept_masteries_concept_id", "concept_masteries", ["concept_id"]
    )
    op.create_index(
        "ix_concept_mastery_user_course",
        "concept_masteries",
        ["user_id", "course_id"],
    )

    for table in COURSE_OWNED_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')

    for table in NEW_TENANT_TABLES:
        _enable_tenant_rls(table)


def downgrade() -> None:
    for table in COURSE_OWNED_TABLES:
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

    for table in reversed(NEW_TENANT_TABLES):
        _disable_tenant_rls(table)

    op.drop_index("ix_concept_mastery_user_course", table_name="concept_masteries")
    op.drop_index("ix_concept_masteries_concept_id", table_name="concept_masteries")
    op.drop_index("ix_concept_masteries_course_id", table_name="concept_masteries")
    op.drop_index("ix_concept_masteries_user_id", table_name="concept_masteries")
    op.drop_table("concept_masteries")
    _delete_private_concepts_for_legacy_schema()

    op.drop_constraint(
        "ck_concept_dependencies_distinct_nodes",
        "concept_dependencies",
        type_="check",
    )
    op.drop_constraint(
        "fk_concept_dependencies_dependent_scope",
        "concept_dependencies",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_concept_dependencies_prerequisite_scope",
        "concept_dependencies",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "concept_dependencies_prerequisite_id_fkey",
        "concept_dependencies",
        "concepts",
        ["prerequisite_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "concept_dependencies_dependent_id_fkey",
        "concept_dependencies",
        "concepts",
        ["dependent_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "fk_concept_dependencies_user", "concept_dependencies", type_="foreignkey"
    )
    op.drop_index(
        "ix_concept_dependencies_user_course", table_name="concept_dependencies"
    )
    op.drop_index(
        "ix_concept_dependencies_course_id", table_name="concept_dependencies"
    )
    op.drop_index("ix_concept_dependencies_user_id", table_name="concept_dependencies")
    op.drop_column("concept_dependencies", "course_id")
    op.drop_column("concept_dependencies", "user_id")

    op.drop_index("ix_concepts_user_course_topic", table_name="concepts")
    op.drop_constraint("uq_concepts_course_name", "concepts", type_="unique")
    op.drop_constraint("uq_concepts_scope", "concepts", type_="unique")
    op.drop_constraint("fk_concepts_course_owner", "concepts", type_="foreignkey")
    op.drop_constraint("fk_concepts_user", "concepts", type_="foreignkey")
    op.drop_index("ix_concepts_course_id", table_name="concepts")
    op.drop_index("ix_concepts_user_id", table_name="concepts")
    op.drop_column("concepts", "course_id")
    op.drop_column("concepts", "user_id")

    op.drop_constraint(
        "fk_mistake_records_question_scope", "mistake_records", type_="foreignkey"
    )
    op.create_foreign_key(
        "mistake_records_question_id_fkey",
        "mistake_records",
        "questions",
        ["question_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "fk_answer_records_question_scope", "answer_records", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_answer_records_quiz_scope", "answer_records", type_="foreignkey"
    )
    op.create_foreign_key(
        "answer_records_question_id_fkey",
        "answer_records",
        "questions",
        ["question_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "answer_records_quiz_session_id_fkey",
        "answer_records",
        "quiz_sessions",
        ["quiz_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("fk_questions_quiz_scope", "questions", type_="foreignkey")
    op.create_foreign_key(
        "questions_quiz_session_id_fkey",
        "questions",
        "quiz_sessions",
        ["quiz_session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "fk_material_chunks_material_scope", "material_chunks", type_="foreignkey"
    )
    op.create_foreign_key(
        "material_chunks_material_id_fkey",
        "material_chunks",
        "materials",
        ["material_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "fk_conversation_messages_conversation_scope",
        "conversation_messages",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "conversation_messages_conversation_id_fkey",
        "conversation_messages",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_index("ix_mistakes_user_course_review", table_name="mistake_records")
    op.drop_index("ix_answer_records_user_course", table_name="answer_records")
    op.drop_index("ix_quiz_sessions_user_course", table_name="quiz_sessions")
    op.drop_index("ix_materials_user_course_status", table_name="materials")
    _collapse_learning_profiles_for_legacy_schema()
    op.drop_constraint(
        "uq_learning_profiles_user_course", "learning_profiles", type_="unique"
    )
    op.drop_index("ix_learning_profiles_user_id", table_name="learning_profiles")
    op.create_index(
        "ix_learning_profiles_user_id",
        "learning_profiles",
        ["user_id"],
        unique=True,
    )

    op.drop_index("ix_conversations_user_course_updated", table_name="conversations")
    op.drop_constraint(
        "ck_conversations_available_minutes_override",
        "conversations",
        type_="check",
    )
    op.drop_column("conversations", "available_minutes_override")

    op.drop_constraint("uq_questions_scope", "questions", type_="unique")
    for table in ("conversation_messages", "material_chunks", "questions"):
        op.drop_index(f"ix_{table}_user_course", table_name=table)
        op.drop_index(f"ix_{table}_course_id", table_name=table)
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_column(table, "course_id")
        op.drop_column(table, "user_id")

    op.drop_constraint("uq_conversations_scope", "conversations", type_="unique")
    op.drop_constraint("uq_materials_scope", "materials", type_="unique")
    op.drop_constraint("uq_quiz_sessions_scope", "quiz_sessions", type_="unique")

    for table in reversed(COURSE_OWNED_TABLES):
        op.drop_constraint(f"fk_{table}_course_owner", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_course_id", table_name=table)
        op.drop_column(table, "course_id")

    for table in COURSE_OWNED_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')

    op.drop_index(
        "ix_study_availability_user_course", table_name="study_availabilities"
    )
    op.drop_index(
        "ix_study_availabilities_course_id", table_name="study_availabilities"
    )
    op.drop_index("ix_study_availabilities_user_id", table_name="study_availabilities")
    op.drop_table("study_availabilities")
    op.drop_index("ix_exams_course_id", table_name="exams")
    op.drop_index("ix_exams_user_id", table_name="exams")
    op.drop_table("exams")
    op.drop_index("ix_courses_user_updated", table_name="courses")
    op.drop_index("ix_courses_user_id", table_name="courses")
    op.drop_index("uq_courses_one_default_per_user", table_name="courses")
    op.drop_table("courses")

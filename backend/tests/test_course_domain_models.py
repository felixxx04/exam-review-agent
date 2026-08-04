from __future__ import annotations

from app.db import models


def test_private_course_domain_models_define_required_entities():
    for model_name in ("Course", "Exam", "StudyAvailability", "ConceptMastery"):
        assert hasattr(models, model_name), f"missing {model_name} model"


def test_course_owned_models_require_a_course_foreign_key():
    for model_name in (
        "Conversation",
        "ConversationMessage",
        "LearningProfile",
        "Material",
        "MaterialChunk",
        "QuizSession",
        "Question",
        "AnswerRecord",
        "MistakeRecord",
        "Concept",
        "ConceptMastery",
    ):
        model = getattr(models, model_name, None)
        assert model is not None, f"missing {model_name} model"
        column = model.__table__.columns.get("course_id")
        assert column is not None, f"{model_name} is not course-scoped"
        assert column.nullable is False


def test_quiz_children_use_course_scoped_composite_foreign_keys():
    expected_constraints = {
        "Question": "fk_questions_quiz_scope",
        "AnswerRecord": "fk_answer_records_question_scope",
        "MistakeRecord": "fk_mistake_records_question_scope",
    }

    for model_name, constraint_name in expected_constraints.items():
        constraint_names = {
            constraint.name
            for constraint in getattr(models, model_name).__table__.constraints
        }
        assert constraint_name in constraint_names


def test_database_allows_at_most_one_default_course_per_user():
    index = next(
        (
            item
            for item in models.Course.__table__.indexes
            if item.name == "uq_courses_one_default_per_user"
        ),
        None,
    )

    assert index is not None
    assert index.unique is True


def test_conversation_supports_a_bounded_temporary_time_override():
    column = models.Conversation.__table__.columns.get("available_minutes_override")

    assert column is not None
    assert column.nullable is True
    constraint_names = {
        constraint.name for constraint in models.Conversation.__table__.constraints
    }
    assert "ck_conversations_available_minutes_override" in constraint_names


def test_course_tenant_indexes_cover_common_list_and_scheduling_queries():
    course_model = getattr(models, "Course", None)
    availability_model = getattr(models, "StudyAvailability", None)
    assert course_model is not None
    assert availability_model is not None

    course_indexes = {index.name for index in course_model.__table__.indexes}
    availability_indexes = {
        index.name for index in availability_model.__table__.indexes
    }
    assert "ix_courses_user_updated" in course_indexes
    assert "ix_study_availability_user_course" in availability_indexes

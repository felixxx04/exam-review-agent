from __future__ import annotations

from app.db import models


def test_private_course_domain_models_define_required_entities():
    for model_name in ("Course", "Exam", "StudyAvailability", "ConceptMastery"):
        assert hasattr(models, model_name), f"missing {model_name} model"


def test_course_owned_models_require_a_course_foreign_key():
    for model_name in (
        "Conversation",
        "LearningProfile",
        "Material",
        "QuizSession",
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

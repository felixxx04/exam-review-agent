import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AnswerRecord,
    Base,
    Concept,
    ConceptDependency,
    Course,
    Conversation,
    ConversationMessage,
    FileType,
    LearningProfile,
    Material,
    MaterialChunk,
    MistakeRecord,
    Question,
    QuestionType,
    QuizSession,
    User,
)


@pytest.fixture
async def engine():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        yield test_engine
    finally:
        await test_engine.dispose()


@pytest.fixture
async def session(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s


async def _create_course(session: AsyncSession, user: User, name: str) -> Course:
    course = Course(user_id=user.id, name=name, is_default=True)
    session.add(course)
    await session.flush()
    return course


@pytest.mark.asyncio
async def test_create_user(session):
    user = User(
        username="test",
        email="test@example.com",
        hashed_password="hashed_xxx",
        display_name="Test User",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.hashed_password == "hashed_xxx"
    assert user.display_name == "Test User"
    assert isinstance(user.created_at, datetime.datetime)


@pytest.mark.asyncio
async def test_user_unique_email(session):
    user1 = User(
        username="dup-one",
        email="dup@example.com",
        hashed_password="pw1",
        display_name="U1",
    )
    user2 = User(
        username="dup-two",
        email="dup@example.com",
        hashed_password="pw2",
        display_name="U2",
    )
    session.add_all([user1, user2])
    with pytest.raises(Exception):
        await session.commit()


@pytest.mark.asyncio
async def test_create_conversation(session):
    user = User(
        username="convuser",
        email="convuser@example.com",
        hashed_password="pw",
        display_name="CU",
    )
    session.add(user)
    await session.commit()
    course = await _create_course(session, user, "Physics")

    conv = Conversation(
        user_id=user.id,
        course_id=course.id,
        title="Physics Review",
        mode="quiz",
        material_scope=[1, 2, 3],
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)

    assert conv.id is not None
    assert conv.user_id == user.id
    assert conv.mode == "quiz"
    assert conv.material_scope == [1, 2, 3]
    assert isinstance(conv.created_at, datetime.datetime)
    assert isinstance(conv.updated_at, datetime.datetime)


@pytest.mark.asyncio
async def test_create_material(session):
    user = User(
        username="matuser",
        email="matuser@example.com",
        hashed_password="pw",
        display_name="MU",
    )
    session.add(user)
    await session.commit()
    course = await _create_course(session, user, "Materials")

    mat = Material(
        user_id=user.id,
        course_id=course.id,
        filename="phys101_upload.pdf",
        original_filename="Physics Chapter 1.pdf",
        file_type="pdf",
        file_size=1048576,
        page_count=42,
        processing_status="pending",
    )
    session.add(mat)
    await session.commit()
    await session.refresh(mat)

    assert mat.id is not None
    assert mat.processing_status == "pending"
    assert mat.page_count == 42


@pytest.mark.asyncio
async def test_create_quiz_session(session):
    user = User(
        username="quizuser",
        email="quizuser@example.com",
        hashed_password="pw",
        display_name="QU",
    )
    session.add(user)
    await session.commit()
    course = await _create_course(session, user, "Quiz")

    quiz = QuizSession(
        user_id=user.id,
        course_id=course.id,
        material_scope=[1, 2],
        question_count=10,
        correct_count=0,
        total_time_seconds=0.0,
        difficulty="medium",
    )
    session.add(quiz)
    await session.commit()
    await session.refresh(quiz)

    assert quiz.id is not None
    assert quiz.difficulty == "medium"


@pytest.mark.asyncio
async def test_create_question(session):
    user = User(
        username="qsuser",
        email="qsuser@example.com",
        hashed_password="pw",
        display_name="QSU",
    )
    session.add(user)
    await session.commit()
    course = await _create_course(session, user, "Questions")

    quiz = QuizSession(
        user_id=user.id,
        course_id=course.id,
        material_scope=[1],
        question_count=1,
        correct_count=0,
        total_time_seconds=0.0,
        difficulty="easy",
    )
    session.add(quiz)
    await session.commit()

    question = Question(
        quiz_session_id=quiz.id,
        user_id=user.id,
        course_id=course.id,
        question_text="What is the speed of light?",
        question_type="multiple_choice",
        options=["3e8 m/s", "3e6 m/s", "3e10 m/s"],
        correct_answer="3e8 m/s",
        explanation="c = 299,792,458 m/s in vacuum",
        difficulty="easy",
        topic="physics",
        concept="speed_of_light",
        source_chunk_ids=["chunk_001", "chunk_002"],
    )
    session.add(question)
    await session.commit()
    await session.refresh(question)

    assert question.id is not None
    assert question.question_type == "multiple_choice"
    assert len(question.options) == 3


@pytest.mark.asyncio
async def test_create_answer_record(session):
    user = User(
        username="aruser",
        email="aruser@example.com",
        hashed_password="pw",
        display_name="ARU",
    )
    session.add(user)
    await session.commit()
    course = await _create_course(session, user, "Answers")

    quiz = QuizSession(
        user_id=user.id,
        course_id=course.id,
        material_scope=[1],
        question_count=1,
        correct_count=0,
        total_time_seconds=0.0,
        difficulty="easy",
    )
    session.add(quiz)
    await session.commit()

    question = Question(
        quiz_session_id=quiz.id,
        user_id=user.id,
        course_id=course.id,
        question_text="What is 2+2?",
        question_type="multiple_choice",
        options=["3", "4", "5"],
        correct_answer="4",
        explanation="Basic addition",
        difficulty="easy",
        topic="math",
        concept="addition",
        source_chunk_ids=[],
    )
    session.add(question)
    await session.commit()

    record = AnswerRecord(
        question_id=question.id,
        user_id=user.id,
        course_id=course.id,
        student_answer="4",
        is_correct=True,
        time_spent_seconds=12.5,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    assert record.id is not None
    assert record.is_correct is True
    assert record.time_spent_seconds == 12.5


@pytest.mark.asyncio
async def test_create_mistake_record(session):
    user = User(
        username="mruser",
        email="mruser@example.com",
        hashed_password="pw",
        display_name="MRU",
    )
    session.add(user)
    await session.commit()
    course = await _create_course(session, user, "Mistakes")

    quiz = QuizSession(
        user_id=user.id,
        course_id=course.id,
        material_scope=[1],
        question_count=1,
        correct_count=0,
        total_time_seconds=0.0,
        difficulty="easy",
    )
    session.add(quiz)
    await session.commit()

    question = Question(
        quiz_session_id=quiz.id,
        user_id=user.id,
        course_id=course.id,
        question_text="What is h2o?",
        question_type="fill_blank",
        options=[],
        correct_answer="Water",
        explanation="H2O is water",
        difficulty="easy",
        topic="chemistry",
        concept="water",
        source_chunk_ids=[],
    )
    session.add(question)
    await session.commit()

    mistake = MistakeRecord(
        user_id=user.id,
        course_id=course.id,
        question_id=question.id,
        concept="water",
        topic="chemistry",
        wrong_answer="Hydrogen",
        correct_answer="Water",
        review_count=0,
        ease_factor=2.5,
    )
    session.add(mistake)
    await session.commit()
    await session.refresh(mistake)

    assert mistake.id is not None
    assert mistake.ease_factor == 2.5
    assert mistake.review_count == 0


@pytest.mark.asyncio
async def test_create_concept_and_dependency(session):
    user = User(
        username="concept-user",
        email="concept@example.com",
        hashed_password="pw",
        display_name="Concept User",
    )
    session.add(user)
    await session.flush()
    course = await _create_course(session, user, "Mathematics")
    prereq = Concept(
        user_id=user.id,
        course_id=course.id,
        topic="math",
        name="Algebra",
        description="Basic algebra concepts",
    )
    dependent = Concept(
        user_id=user.id,
        course_id=course.id,
        topic="math",
        name="Calculus",
        description="Differential and integral calculus",
    )
    session.add_all([prereq, dependent])
    await session.commit()

    dep = ConceptDependency(
        user_id=user.id,
        course_id=course.id,
        prerequisite_id=prereq.id,
        dependent_id=dependent.id,
    )
    session.add(dep)
    await session.commit()
    await session.refresh(dep)

    assert dep.id is not None
    assert dep.prerequisite_id == prereq.id
    assert dep.dependent_id == dependent.id


@pytest.mark.asyncio
async def test_user_cascade_conversations(session):
    """Deleting a user should cascade to their conversations."""
    user = User(
        username="cascade",
        email="cascade@example.com",
        hashed_password="pw",
        display_name="Cascade",
    )
    session.add(user)
    await session.commit()
    course = await _create_course(session, user, "Cascade")

    conv = Conversation(
        user_id=user.id,
        course_id=course.id,
        title="Test",
        mode="ask",
        material_scope=[],
    )
    session.add(conv)
    await session.commit()

    await session.delete(user)
    await session.commit()

    result = await session.execute(
        text("SELECT COUNT(*) FROM conversations WHERE user_id = :uid"),
        {"uid": user.id},
    )
    count = result.scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_material_processing_status_transition(session):
    user = User(
        username="status",
        email="status@example.com",
        hashed_password="pw",
        display_name="ST",
    )
    session.add(user)
    await session.commit()
    course = await _create_course(session, user, "Status")

    mat = Material(
        user_id=user.id,
        course_id=course.id,
        filename="test.docx",
        original_filename="test.docx",
        file_type="docx",
        file_size=5000,
        page_count=1,
        processing_status="processing",
    )
    session.add(mat)
    await session.commit()

    # Transition to ready
    mat.processing_status = "ready"
    mat.chunk_count = 15
    await session.commit()
    await session.refresh(mat)

    assert mat.processing_status == "ready"
    assert mat.chunk_count == 15


@pytest.mark.asyncio
async def test_conversation_message_model(session):
    user = User(
        username="memory",
        email="memory@example.com",
        hashed_password="hashed",
        display_name="Memory User",
    )
    session.add(user)
    await session.flush()
    course = await _create_course(session, user, "Memory")

    conversation = Conversation(
        user_id=user.id,
        course_id=course.id,
        title="复习数据库",
    )
    session.add(conversation)
    await session.flush()

    message = ConversationMessage(
        conversation_id=conversation.id,
        user_id=user.id,
        course_id=course.id,
        role="user",
        content="刚才那个概念再举个例子",
        material_scope=["database.pdf"],
        message_metadata={"mode": "ask", "intent": "qa"},
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)

    assert message.id is not None
    assert message.conversation_id == conversation.id
    assert message.material_scope == ["database.pdf"]
    assert message.message_metadata["intent"] == "qa"


@pytest.mark.asyncio
async def test_learning_profile_model(session):
    user = User(
        username="profile",
        email="profile@example.com",
        hashed_password="hashed",
        display_name="Profile User",
    )
    session.add(user)
    await session.flush()
    course = await _create_course(session, user, "Profile")

    profile = LearningProfile(
        user_id=user.id,
        course_id=course.id,
        current_subject="数据库系统",
        review_goal="理解事务隔离级别",
        weak_concepts=["幻读"],
        frequent_questions=["隔离级别区别"],
        active_materials=["database.pdf"],
        preferences={"answer_style": "examples"},
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)

    assert profile.current_subject == "数据库系统"
    assert profile.weak_concepts == ["幻读"]
    assert profile.preferences["answer_style"] == "examples"


@pytest.mark.asyncio
async def test_material_chunk_and_extended_fields(session):
    user = User(
        username="chunk",
        email="chunk@example.com",
        hashed_password="hashed",
        display_name="Chunk User",
    )
    session.add(user)
    await session.flush()
    course = await _create_course(session, user, "Chunks")

    material = Material(
        user_id=user.id,
        course_id=course.id,
        filename="stored.pdf",
        original_filename="database.pdf",
        file_type=FileType.PDF,
        file_size=128,
        storage_path="uploads/stored.pdf",
        mime_type="application/pdf",
        hash="abc123",
        processed_at=datetime.datetime.now(datetime.UTC),
    )
    session.add(material)
    await session.flush()

    chunk = MaterialChunk(
        material_id=material.id,
        user_id=user.id,
        course_id=course.id,
        chunk_id="chunk-1",
        text_preview="事务隔离级别",
        page_number=3,
        token_count=42,
        embedding_id="chunk-1",
    )
    session.add(chunk)
    await session.commit()
    await session.refresh(chunk)

    assert chunk.material_id == material.id
    assert chunk.page_number == 3
    assert material.storage_path == "uploads/stored.pdf"


def test_material_chunk_has_v2_retrieval_columns():
    columns = MaterialChunk.__table__.columns

    assert columns["content"].nullable is False
    assert columns["content_hash"].nullable is False
    assert columns["lexical_tokens"].nullable is False
    assert columns["embedding_model"].nullable is True
    assert columns["embedding"].type.dim == 1024


def test_mistake_record_supports_review_workbench_without_persisted_question():
    columns = MistakeRecord.__table__.columns

    assert columns["question_id"].nullable is True
    assert columns["source_question_id"].nullable is False
    for field in (
        "question_text",
        "question_type",
        "explanation",
        "source_chunk_ids",
        "source_material",
        "status",
        "attempt_count",
        "last_wrong_at",
        "correction_note",
        "mastered_at",
        "review_history",
    ):
        assert field in columns


def test_v2_models_define_tenant_and_scheduling_indexes():
    material_indexes = {index.name for index in Material.__table__.indexes}
    mistake_indexes = {index.name for index in MistakeRecord.__table__.indexes}

    assert "ix_materials_user_status" in material_indexes
    assert "ix_mistakes_user_status_review" in mistake_indexes
    assert "ix_mistakes_user_concept" in mistake_indexes


def test_v2_timestamp_columns_are_timezone_aware():
    timestamp_columns = [
        User.created_at,
        Conversation.created_at,
        Conversation.updated_at,
        Material.created_at,
        Material.processed_at,
        QuizSession.created_at,
        AnswerRecord.created_at,
        MistakeRecord.last_wrong_at,
        MistakeRecord.mastered_at,
        MistakeRecord.next_review_at,
    ]

    assert all(column.type.timezone is True for column in timestamp_columns)


@pytest.mark.asyncio
async def test_answer_record_extended_fields(session):
    user = User(
        username="answer",
        email="answer@example.com",
        hashed_password="hashed",
        display_name="Answer User",
    )
    session.add(user)
    await session.flush()
    course = await _create_course(session, user, "Extended Answers")

    quiz = QuizSession(
        user_id=user.id,
        course_id=course.id,
        question_count=1,
    )
    session.add(quiz)
    await session.flush()

    question = Question(
        quiz_session_id=quiz.id,
        user_id=user.id,
        course_id=course.id,
        question_text="事务的 I 代表什么？",
        question_type=QuestionType.FILL_BLANK,
        correct_answer="Isolation",
    )
    session.add(question)
    await session.flush()

    record = AnswerRecord(
        question_id=question.id,
        quiz_session_id=quiz.id,
        user_id=user.id,
        course_id=course.id,
        student_answer="Isolation",
        is_correct=True,
        feedback="回答正确",
        score=1.0,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    assert record.quiz_session_id == quiz.id
    assert record.feedback == "回答正确"
    assert record.score == 1.0

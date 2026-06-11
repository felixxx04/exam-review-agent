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
    Conversation,
    Material,
    MistakeRecord,
    Question,
    QuizSession,
    User,
)


@pytest.fixture
def engine():
    return create_async_engine("sqlite+aiosqlite:///:memory:")


@pytest.fixture
async def session(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s


@pytest.mark.asyncio
async def test_create_user(session):
    user = User(
        email="test@example.com", hashed_password="hashed_xxx", display_name="Test User"
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
    user1 = User(email="dup@example.com", hashed_password="pw1", display_name="U1")
    user2 = User(email="dup@example.com", hashed_password="pw2", display_name="U2")
    session.add_all([user1, user2])
    with pytest.raises(Exception):
        await session.commit()


@pytest.mark.asyncio
async def test_create_conversation(session):
    user = User(email="convuser@example.com", hashed_password="pw", display_name="CU")
    session.add(user)
    await session.commit()

    conv = Conversation(
        user_id=user.id,
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
    user = User(email="matuser@example.com", hashed_password="pw", display_name="MU")
    session.add(user)
    await session.commit()

    mat = Material(
        user_id=user.id,
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
    user = User(email="quizuser@example.com", hashed_password="pw", display_name="QU")
    session.add(user)
    await session.commit()

    quiz = QuizSession(
        user_id=user.id,
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
    user = User(email="qsuser@example.com", hashed_password="pw", display_name="QSU")
    session.add(user)
    await session.commit()

    quiz = QuizSession(
        user_id=user.id,
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
    user = User(email="aruser@example.com", hashed_password="pw", display_name="ARU")
    session.add(user)
    await session.commit()

    quiz = QuizSession(
        user_id=user.id,
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
    user = User(email="mruser@example.com", hashed_password="pw", display_name="MRU")
    session.add(user)
    await session.commit()

    quiz = QuizSession(
        user_id=user.id,
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
    prereq = Concept(topic="math", name="Algebra", description="Basic algebra concepts")
    dependent = Concept(
        topic="math", name="Calculus", description="Differential and integral calculus"
    )
    session.add_all([prereq, dependent])
    await session.commit()

    dep = ConceptDependency(prerequisite_id=prereq.id, dependent_id=dependent.id)
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
        email="cascade@example.com", hashed_password="pw", display_name="Cascade"
    )
    session.add(user)
    await session.commit()

    conv = Conversation(
        user_id=user.id, title="Test", mode="ask", material_scope=[]
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
    user = User(email="status@example.com", hashed_password="pw", display_name="ST")
    session.add(user)
    await session.commit()

    mat = Material(
        user_id=user.id,
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

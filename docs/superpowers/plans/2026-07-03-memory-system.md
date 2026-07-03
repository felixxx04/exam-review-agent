# Memory System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable cross-session memory for the local default-user exam review Agent.

**Architecture:** Add relational persistence for conversation messages, learning profile, and material chunks, then route chat requests through a focused `MemoryService`. The Agent receives bounded memory context made from the learning profile, conversation summary, and recent messages, while the frontend restores chat history from the backend.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic, SQLite for local development, LangGraph/LangChain messages, Next.js, React, Zustand, Vitest, pytest.

---

## Execution Notes

- The worktree may contain unrelated local changes. For every task, stage only the files listed in that task.
- Keep `user_id="default"` for Agent memory behavior, but database rows still use the existing integer `User.id` foreign keys where models require them.
- Do not store local secrets in code, docs, summaries, learning profiles, migrations, tests, or fixtures.
- Prefer small commits. Each task below ends with its own commit.

## File Structure

- `backend/app/db/models.py`: SQLAlchemy models and relationships.
- `backend/alembic/versions/20260703_0001_memory_system.py`: migration for new memory tables and columns.
- `backend/app/schemas/chat.py`: chat request and stream payload schemas.
- `backend/app/schemas/conversations.py`: conversation and message response schemas.
- `backend/app/schemas/memory.py`: learning profile response schema.
- `backend/app/services/memory_service.py`: memory persistence, context building, summary thresholds, profile merge policy.
- `backend/app/api/conversations.py`: active conversation and message history endpoints.
- `backend/app/api/memory.py`: learning profile endpoint.
- `backend/app/api/chat.py`: chat endpoint integration with `MemoryService`.
- `backend/app/orchestrator/state.py`: memory context fields in graph state.
- `backend/app/orchestrator/graph.py`: orchestrator input and message construction.
- `backend/app/api/materials.py`: material metadata and chunk-row cleanup integration.
- `frontend/src/lib/api.ts`: conversation and memory API client methods.
- `frontend/src/stores/chatStore.ts`: `conversationId` and history restore state.
- `frontend/src/hooks/useChatStream.ts`: send `conversation_id` and handle stream metadata.
- `frontend/src/app/page.tsx`: load active conversation history on first render.

## Task 1: Database Models And Migration

**Files:**
- Modify: `backend/app/db/models.py`
- Create: `backend/alembic/versions/20260703_0001_memory_system.py`
- Test: `backend/tests/test_db_models.py`

- [ ] **Step 1: Add failing model tests**

Add these tests to `backend/tests/test_db_models.py`:

```python
import datetime

import pytest

from app.db.models import (
    AnswerRecord,
    Conversation,
    ConversationMessage,
    FileType,
    LearningProfile,
    Material,
    MaterialChunk,
    Question,
    QuestionType,
    QuizSession,
    User,
)


@pytest.mark.asyncio
async def test_conversation_message_model(db_session):
    user = User(
        email="memory@example.com",
        hashed_password="hashed",
        display_name="Memory User",
    )
    db_session.add(user)
    await db_session.flush()

    conversation = Conversation(user_id=user.id, title="复习数据库")
    db_session.add(conversation)
    await db_session.flush()

    message = ConversationMessage(
        conversation_id=conversation.id,
        role="user",
        content="刚才那个概念再举个例子",
        material_scope=["database.pdf"],
        message_metadata={"mode": "ask", "intent": "qa"},
    )
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(message)

    assert message.id is not None
    assert message.conversation_id == conversation.id
    assert message.material_scope == ["database.pdf"]
    assert message.message_metadata["intent"] == "qa"


@pytest.mark.asyncio
async def test_learning_profile_model(db_session):
    user = User(
        email="profile@example.com",
        hashed_password="hashed",
        display_name="Profile User",
    )
    db_session.add(user)
    await db_session.flush()

    profile = LearningProfile(
        user_id=user.id,
        current_subject="数据库系统",
        review_goal="理解事务隔离级别",
        weak_concepts=["幻读"],
        frequent_questions=["隔离级别区别"],
        active_materials=["database.pdf"],
        preferences={"answer_style": "examples"},
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    assert profile.current_subject == "数据库系统"
    assert profile.weak_concepts == ["幻读"]
    assert profile.preferences["answer_style"] == "examples"


@pytest.mark.asyncio
async def test_material_chunk_and_extended_fields(db_session):
    user = User(
        email="chunk@example.com",
        hashed_password="hashed",
        display_name="Chunk User",
    )
    db_session.add(user)
    await db_session.flush()

    material = Material(
        user_id=user.id,
        filename="stored.pdf",
        original_filename="database.pdf",
        file_type=FileType.PDF,
        file_size=128,
        storage_path="uploads/stored.pdf",
        mime_type="application/pdf",
        hash="abc123",
        processed_at=datetime.datetime.now(datetime.UTC),
    )
    db_session.add(material)
    await db_session.flush()

    chunk = MaterialChunk(
        material_id=material.id,
        chunk_id="chunk-1",
        text_preview="事务隔离级别",
        page_number=3,
        token_count=42,
        embedding_id="chunk-1",
    )
    db_session.add(chunk)
    await db_session.commit()
    await db_session.refresh(chunk)

    assert chunk.material_id == material.id
    assert chunk.page_number == 3
    assert material.storage_path == "uploads/stored.pdf"


@pytest.mark.asyncio
async def test_answer_record_extended_fields(db_session):
    user = User(
        email="answer@example.com",
        hashed_password="hashed",
        display_name="Answer User",
    )
    db_session.add(user)
    await db_session.flush()

    session = QuizSession(user_id=user.id, question_count=1)
    db_session.add(session)
    await db_session.flush()

    question = Question(
        quiz_session_id=session.id,
        question_text="事务的 I 代表什么？",
        question_type=QuestionType.FILL_BLANK,
        correct_answer="Isolation",
    )
    db_session.add(question)
    await db_session.flush()

    record = AnswerRecord(
        question_id=question.id,
        quiz_session_id=session.id,
        user_id=user.id,
        student_answer="Isolation",
        is_correct=True,
        feedback="回答正确",
        score=1.0,
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    assert record.quiz_session_id == session.id
    assert record.feedback == "回答正确"
    assert record.score == 1.0
```

- [ ] **Step 2: Run model tests and verify failure**

Run:

```bash
cd backend
.venv\Scripts\pytest tests/test_db_models.py -q
```

Expected: FAIL with import or attribute errors for `ConversationMessage`, `LearningProfile`, `MaterialChunk`, or the new fields.

- [ ] **Step 3: Add model classes and fields**

Modify `backend/app/db/models.py` with these additions:

```python
class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
```

Extend `User` relationships:

```python
    learning_profiles = relationship("LearningProfile", back_populates="user", cascade="all, delete-orphan")
```

Extend `Conversation`:

```python
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_message_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    last_memory_updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan")
```

Add after `Conversation`:

```python
class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(SAEnum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    material_scope: Mapped[list | None] = mapped_column(JSON, nullable=True)
    message_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    conversation = relationship("Conversation", back_populates="messages")
```

Add after `Material`:

```python
class MaterialChunk(Base):
    __tablename__ = "material_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    text_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    material = relationship("Material", back_populates="chunks")
```

Extend `Material`:

```python
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    processed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunks = relationship("MaterialChunk", back_populates="material", cascade="all, delete-orphan")
```

Add after `User`:

```python
class LearningProfile(Base):
    __tablename__ = "learning_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    current_subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    review_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    weak_concepts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    frequent_questions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    active_materials: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    user = relationship("User", back_populates="learning_profiles")
```

Extend `AnswerRecord`:

```python
    quiz_session_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("quiz_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
```

- [ ] **Step 4: Add Alembic migration**

Create `backend/alembic/versions/20260703_0001_memory_system.py`:

```python
"""add memory system tables

Revision ID: 20260703_0001
Revises: 06c68121755a
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260703_0001"
down_revision = "06c68121755a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("conversations", sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("conversations", sa.Column("last_message_at", sa.DateTime(), nullable=True))
    op.add_column("conversations", sa.Column("last_memory_updated_at", sa.DateTime(), nullable=True))

    op.add_column("materials", sa.Column("storage_path", sa.String(length=1000), nullable=True))
    op.add_column("materials", sa.Column("mime_type", sa.String(length=255), nullable=True))
    op.add_column("materials", sa.Column("hash", sa.String(length=128), nullable=True))
    op.add_column("materials", sa.Column("processed_at", sa.DateTime(), nullable=True))
    op.add_column("materials", sa.Column("parse_error", sa.Text(), nullable=True))
    op.create_index("ix_materials_hash", "materials", ["hash"])

    op.add_column("answer_records", sa.Column("quiz_session_id", sa.Integer(), nullable=True))
    op.add_column("answer_records", sa.Column("feedback", sa.Text(), nullable=True))
    op.add_column("answer_records", sa.Column("score", sa.Float(), nullable=True))
    op.create_index("ix_answer_records_quiz_session_id", "answer_records", ["quiz_session_id"])
    op.create_foreign_key(
        "fk_answer_records_quiz_session_id_quiz_sessions",
        "answer_records",
        "quiz_sessions",
        ["quiz_session_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Enum("USER", "ASSISTANT", "SYSTEM", name="messagerole"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("material_scope", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_conversation_messages_conversation_id", "conversation_messages", ["conversation_id"])

    op.create_table(
        "learning_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("current_subject", sa.String(length=200), nullable=True),
        sa.Column("review_goal", sa.Text(), nullable=True),
        sa.Column("weak_concepts", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("frequent_questions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("active_materials", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("preferences", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_learning_profiles_user_id", "learning_profiles", ["user_id"], unique=True)

    op.create_table(
        "material_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.String(length=100), nullable=False),
        sa.Column("text_preview", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("chunk_id"),
    )
    op.create_index("ix_material_chunks_material_id", "material_chunks", ["material_id"])
    op.create_index("ix_material_chunks_chunk_id", "material_chunks", ["chunk_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_material_chunks_chunk_id", table_name="material_chunks")
    op.drop_index("ix_material_chunks_material_id", table_name="material_chunks")
    op.drop_table("material_chunks")

    op.drop_index("ix_learning_profiles_user_id", table_name="learning_profiles")
    op.drop_table("learning_profiles")

    op.drop_index("ix_conversation_messages_conversation_id", table_name="conversation_messages")
    op.drop_table("conversation_messages")

    op.drop_constraint("fk_answer_records_quiz_session_id_quiz_sessions", "answer_records", type_="foreignkey")
    op.drop_index("ix_answer_records_quiz_session_id", table_name="answer_records")
    op.drop_column("answer_records", "score")
    op.drop_column("answer_records", "feedback")
    op.drop_column("answer_records", "quiz_session_id")

    op.drop_index("ix_materials_hash", table_name="materials")
    op.drop_column("materials", "parse_error")
    op.drop_column("materials", "processed_at")
    op.drop_column("materials", "hash")
    op.drop_column("materials", "mime_type")
    op.drop_column("materials", "storage_path")

    op.drop_column("conversations", "last_memory_updated_at")
    op.drop_column("conversations", "last_message_at")
    op.drop_column("conversations", "message_count")
    op.drop_column("conversations", "summary")
```

- [ ] **Step 5: Run model tests and migration check**

Run:

```bash
cd backend
.venv\Scripts\pytest tests/test_db_models.py -q
.venv\Scripts\alembic upgrade head
```

Expected: tests PASS and Alembic upgrades the local SQLite database without errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/20260703_0001_memory_system.py backend/tests/test_db_models.py
git commit -m "feat: add memory database models"
```

## Task 2: Memory Service Foundation

**Files:**
- Create: `backend/app/services/memory_service.py`
- Test: `backend/tests/test_services/test_memory_service.py`

- [ ] **Step 1: Write failing service tests**

Create `backend/tests/test_services/test_memory_service.py`:

```python
from __future__ import annotations

import pytest

from app.services.memory_service import MemoryService


@pytest.mark.asyncio
async def test_get_or_create_default_conversation(db_session):
    service = MemoryService(db_session)

    conversation = await service.get_or_create_active_conversation(user_id="default")
    same_conversation = await service.get_or_create_active_conversation(user_id="default")

    assert conversation.id == same_conversation.id
    assert conversation.title == "默认复习会话"


@pytest.mark.asyncio
async def test_save_messages_and_build_context(db_session):
    service = MemoryService(db_session)
    conversation = await service.get_or_create_active_conversation(user_id="default")

    await service.save_message(
        conversation_id=conversation.id,
        role="user",
        content="什么是幻读？",
        material_scope=["database.pdf"],
        metadata={"mode": "ask"},
    )
    await service.save_message(
        conversation_id=conversation.id,
        role="assistant",
        content="幻读是同一事务中再次查询出现新增行。",
        material_scope=["database.pdf"],
        metadata={"citations": [{"source": "database.pdf", "page": 3}]},
    )

    context = await service.build_memory_context(
        conversation_id=conversation.id,
        user_id="default",
        material_scope=["database.pdf"],
    )

    assert context["conversation_id"] == conversation.id
    assert context["learning_profile"]["weak_concepts"] == []
    assert len(context["recent_messages"]) == 2
    assert context["recent_messages"][0]["role"] == "user"
    assert context["recent_messages"][1]["content"] == "幻读是同一事务中再次查询出现新增行。"


@pytest.mark.asyncio
async def test_profile_merge_is_conservative(db_session):
    service = MemoryService(db_session)
    profile = await service.get_or_create_learning_profile(user_id="default")

    await service.merge_learning_profile(
        profile=profile,
        extracted={
            "current_subject": "数据库系统",
            "review_goal": "理解事务隔离级别",
            "weak_concepts": ["幻读", "幻读", "可重复读"],
            "frequent_questions": ["隔离级别区别"],
            "active_materials": ["database.pdf"],
            "preferences": {"answer_style": "examples"},
            "ignored_field": "ignored",
        },
    )

    assert profile.current_subject == "数据库系统"
    assert profile.weak_concepts == ["幻读", "可重复读"]
    assert profile.frequent_questions == ["隔离级别区别"]
    assert profile.active_materials == ["database.pdf"]
    assert profile.preferences == {"answer_style": "examples"}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd backend
.venv\Scripts\pytest tests/test_services/test_memory_service.py -q
```

Expected: FAIL because `app.services.memory_service` does not exist.

- [ ] **Step 3: Implement `MemoryService`**

Create `backend/app/services/memory_service.py`:

```python
from __future__ import annotations

import datetime
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, ConversationMessage, LearningProfile, MessageRole, User


DEFAULT_USER_EMAIL = "default@example.local"
DEFAULT_USER_NAME = "Default User"
RECENT_MESSAGE_LIMIT = 12
SUMMARY_MESSAGE_INTERVAL = 6


class MemoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create_default_user(self, user_id: str = "default") -> User:
        result = await self.db.execute(select(User).where(User.email == f"{user_id}@example.local"))
        user = result.scalar_one_or_none()
        if user is not None:
            return user

        user = User(
            email=f"{user_id}@example.local",
            hashed_password="local-memory-user",
            display_name=DEFAULT_USER_NAME,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_or_create_active_conversation(self, user_id: str = "default") -> Conversation:
        user = await self.get_or_create_default_user(user_id)
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
        conversation = result.scalar_one_or_none()
        if conversation is not None:
            return conversation

        conversation = Conversation(user_id=user.id, title="默认复习会话")
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def get_or_create_learning_profile(self, user_id: str = "default") -> LearningProfile:
        user = await self.get_or_create_default_user(user_id)
        result = await self.db.execute(select(LearningProfile).where(LearningProfile.user_id == user.id))
        profile = result.scalar_one_or_none()
        if profile is not None:
            return profile

        profile = LearningProfile(
            user_id=user.id,
            weak_concepts=[],
            frequent_questions=[],
            active_materials=[],
            preferences={},
        )
        self.db.add(profile)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    async def save_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        material_scope: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationMessage:
        message = ConversationMessage(
            conversation_id=conversation_id,
            role=MessageRole(role),
            content=content,
            material_scope=material_scope,
            message_metadata=metadata or {},
        )
        conversation = await self.db.get(Conversation, conversation_id)
        if conversation is not None:
            now = datetime.datetime.now(datetime.UTC)
            conversation.message_count = (conversation.message_count or 0) + 1
            conversation.last_message_at = now
            conversation.updated_at = now
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_recent_messages(self, conversation_id: int, limit: int = RECENT_MESSAGE_LIMIT) -> list[ConversationMessage]:
        result = await self.db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def build_memory_context(
        self,
        conversation_id: int,
        user_id: str = "default",
        material_scope: list[str] | None = None,
    ) -> dict[str, Any]:
        conversation = await self.db.get(Conversation, conversation_id)
        profile = await self.get_or_create_learning_profile(user_id)
        recent = await self.get_recent_messages(conversation_id)
        return {
            "conversation_id": conversation_id,
            "summary": conversation.summary if conversation else None,
            "recent_messages": [
                {"role": str(m.role.value if hasattr(m.role, "value") else m.role), "content": m.content}
                for m in recent
            ],
            "learning_profile": self.profile_to_dict(profile),
            "material_scope": material_scope or [],
        }

    def should_update_summary(self, conversation: Conversation) -> bool:
        return conversation.message_count > 0 and conversation.message_count % SUMMARY_MESSAGE_INTERVAL == 0

    async def merge_learning_profile(self, profile: LearningProfile, extracted: dict[str, Any]) -> LearningProfile:
        if isinstance(extracted.get("current_subject"), str) and extracted["current_subject"].strip():
            profile.current_subject = extracted["current_subject"].strip()
        if isinstance(extracted.get("review_goal"), str) and extracted["review_goal"].strip():
            profile.review_goal = extracted["review_goal"].strip()
        profile.weak_concepts = self._merge_list(profile.weak_concepts, extracted.get("weak_concepts"))
        profile.frequent_questions = self._merge_list(profile.frequent_questions, extracted.get("frequent_questions"), limit=10)
        profile.active_materials = self._merge_list(profile.active_materials, extracted.get("active_materials"), limit=20)
        if isinstance(extracted.get("preferences"), dict):
            profile.preferences = {**(profile.preferences or {}), **extracted["preferences"]}
        profile.updated_at = datetime.datetime.now(datetime.UTC)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    def to_langchain_messages(self, memory_context: dict[str, Any], current_message: str) -> list:
        system_parts = []
        learning_profile = memory_context.get("learning_profile") or {}
        if learning_profile:
            system_parts.append(f"用户学习状态: {learning_profile}")
        if memory_context.get("summary"):
            system_parts.append(f"本会话摘要: {memory_context['summary']}")

        messages = []
        if system_parts:
            messages.append(SystemMessage(content="\n".join(system_parts)))
        for item in memory_context.get("recent_messages", []):
            if item["role"] == "assistant":
                messages.append(AIMessage(content=item["content"]))
            elif item["role"] == "user":
                messages.append(HumanMessage(content=item["content"]))
        messages.append(HumanMessage(content=current_message))
        return messages

    @staticmethod
    def profile_to_dict(profile: LearningProfile) -> dict[str, Any]:
        return {
            "current_subject": profile.current_subject,
            "review_goal": profile.review_goal,
            "weak_concepts": profile.weak_concepts or [],
            "frequent_questions": profile.frequent_questions or [],
            "active_materials": profile.active_materials or [],
            "preferences": profile.preferences or {},
        }

    @staticmethod
    def _merge_list(existing: list | None, incoming: Any, limit: int = 20) -> list:
        merged = list(existing or [])
        if not isinstance(incoming, list):
            return merged[:limit]
        for value in incoming:
            if isinstance(value, str):
                normalized = value.strip()
                if normalized and normalized not in merged:
                    merged.append(normalized)
        return merged[-limit:]
```

- [ ] **Step 4: Run service tests**

Run:

```bash
cd backend
.venv\Scripts\pytest tests/test_services/test_memory_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/memory_service.py backend/tests/test_services/test_memory_service.py
git commit -m "feat: add memory service foundation"
```

## Task 3: Conversation And Memory APIs

**Files:**
- Create: `backend/app/schemas/conversations.py`
- Create: `backend/app/schemas/memory.py`
- Create: `backend/app/api/conversations.py`
- Create: `backend/app/api/memory.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api/test_conversations.py`
- Test: `backend/tests/test_api/test_memory.py`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_api/test_conversations.py`:

```python
from __future__ import annotations

import pytest


def _data(response):
    body = response.json()
    assert body["success"] is True
    return body["data"]


@pytest.mark.asyncio
async def test_get_active_conversation(client_with_db):
    response = await client_with_db.get("/api/conversations/active")

    assert response.status_code == 200
    data = _data(response)
    assert data["id"] > 0
    assert data["title"] == "默认复习会话"
    assert data["message_count"] == 0


@pytest.mark.asyncio
async def test_get_conversation_messages(client_with_db):
    active = await client_with_db.get("/api/conversations/active")
    conversation_id = _data(active)["id"]

    response = await client_with_db.get(f"/api/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    data = _data(response)
    assert data["conversation_id"] == conversation_id
    assert data["messages"] == []
```

Create `backend/tests/test_api/test_memory.py`:

```python
from __future__ import annotations

import pytest


def _data(response):
    body = response.json()
    assert body["success"] is True
    return body["data"]


@pytest.mark.asyncio
async def test_get_memory_profile(client_with_db):
    response = await client_with_db.get("/api/memory/profile")

    assert response.status_code == 200
    data = _data(response)
    assert data["weak_concepts"] == []
    assert data["frequent_questions"] == []
    assert data["active_materials"] == []
    assert data["preferences"] == {}
```

- [ ] **Step 2: Run API tests and verify failure**

Run:

```bash
cd backend
.venv\Scripts\pytest tests/test_api/test_conversations.py tests/test_api/test_memory.py -q
```

Expected: FAIL with 404 responses because the routers are not registered.

- [ ] **Step 3: Add schemas**

Create `backend/app/schemas/conversations.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConversationResponse(BaseModel):
    id: int
    title: str
    summary: str | None = None
    message_count: int
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationMessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    material_scope: list[str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ConversationMessagesResponse(BaseModel):
    conversation_id: int
    messages: list[ConversationMessageResponse]
```

Create `backend/app/schemas/memory.py`:

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LearningProfileResponse(BaseModel):
    current_subject: str | None = None
    review_goal: str | None = None
    weak_concepts: list[str]
    frequent_questions: list[str]
    active_materials: list[str]
    preferences: dict
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 4: Add routers**

Create `backend/app/api/conversations.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Conversation
from app.schemas.common import ApiResponse
from app.schemas.conversations import (
    ConversationMessageResponse,
    ConversationMessagesResponse,
    ConversationResponse,
)
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("/active")
async def get_active_conversation(db: AsyncSession = Depends(get_db)):
    service = MemoryService(db)
    conversation = await service.get_or_create_active_conversation(user_id="default")
    return ApiResponse.ok(data=ConversationResponse.model_validate(conversation))


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
):
    service = MemoryService(db)
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = await service.get_recent_messages(conversation_id, limit=100)
    data = ConversationMessagesResponse(
        conversation_id=conversation_id,
        messages=[
            ConversationMessageResponse(
                id=m.id,
                conversation_id=m.conversation_id,
                role=str(m.role.value if hasattr(m.role, "value") else m.role),
                content=m.content,
                material_scope=m.material_scope,
                metadata=m.message_metadata or {},
                created_at=m.created_at,
            )
            for m in messages
        ],
    )
    return ApiResponse.ok(data=data)
```

Create `backend/app/api/memory.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.memory import LearningProfileResponse
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/profile")
async def get_memory_profile(db: AsyncSession = Depends(get_db)):
    service = MemoryService(db)
    profile = await service.get_or_create_learning_profile(user_id="default")
    return ApiResponse.ok(data=LearningProfileResponse.model_validate(profile))
```

- [ ] **Step 5: Register routers**

Modify `backend/app/main.py`:

```python
from app.api.conversations import router as conversations_router
from app.api.memory import router as memory_router
```

Add router registration near the existing routers:

```python
app.include_router(conversations_router)
app.include_router(memory_router)
```

- [ ] **Step 6: Run API tests**

Run:

```bash
cd backend
.venv\Scripts\pytest tests/test_api/test_conversations.py tests/test_api/test_memory.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/conversations.py backend/app/schemas/memory.py backend/app/api/conversations.py backend/app/api/memory.py backend/app/main.py backend/app/services/memory_service.py backend/tests/test_api/test_conversations.py backend/tests/test_api/test_memory.py
git commit -m "feat: expose memory conversation APIs"
```

## Task 4: Chat Persistence Integration

**Files:**
- Modify: `backend/app/schemas/chat.py`
- Modify: `backend/app/api/chat.py`
- Test: `backend/tests/test_api/test_chat.py`

- [ ] **Step 1: Add failing chat persistence tests**

Add to `backend/tests/test_api/test_chat.py`:

```python
import json

from sqlalchemy import select

from app.db.models import ConversationMessage


@pytest.mark.asyncio
async def test_chat_persists_user_and_assistant_messages(client_with_db, db_session, monkeypatch):
    async def fake_run_orchestrator(*args, **kwargs):
        return {"messages": [AIMessage(content="可以，继续解释幻读。")]}

    monkeypatch.setattr("app.api.chat.run_orchestrator", fake_run_orchestrator)

    response = await client_with_db.post(
        "/api/chat",
        json={"message": "刚才那个概念再举个例子", "material_scope": ["database.pdf"]},
    )

    assert response.status_code == 200
    rows = (
        await db_session.execute(
            select(ConversationMessage).order_by(ConversationMessage.created_at.asc())
        )
    ).scalars().all()
    assert [str(row.role.value if hasattr(row.role, "value") else row.role) for row in rows] == ["user", "assistant"]
    assert rows[0].content == "刚才那个概念再举个例子"
    assert rows[1].content == "可以，继续解释幻读。"


@pytest.mark.asyncio
async def test_chat_stream_includes_conversation_id(client_with_db, monkeypatch):
    async def fake_run_orchestrator(*args, **kwargs):
        return {"messages": [AIMessage(content="测试回复")]}

    monkeypatch.setattr("app.api.chat.run_orchestrator", fake_run_orchestrator)

    response = await client_with_db.post("/api/chat", json={"message": "继续"})

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert any(event["event"] == "conversation" and event["data"]["id"] > 0 for event in events)
```

- [ ] **Step 2: Run chat tests and verify failure**

Run:

```bash
cd backend
.venv\Scripts\pytest tests/test_api/test_chat.py -q
```

Expected: FAIL because chat does not persist messages or emit conversation metadata.

- [ ] **Step 3: Extend chat request schema**

Modify `backend/app/schemas/chat.py`:

```python
class ChatRequest(BaseModel):
    message: str
    material_scope: list[str] | None = None
    conversation_id: int | None = None
```

- [ ] **Step 4: Update chat endpoint**

Modify `backend/app/api/chat.py`:

```python
from app.db.database import get_db
from app.db.models import Conversation
from app.services.memory_service import MemoryService
from sqlalchemy.ext.asyncio import AsyncSession
```

Change the endpoint signature:

```python
async def chat(
    request: ChatRequest = Depends(_guard_prompt),
    db: AsyncSession = Depends(get_db),
):
```

Inside `chat`, create the service before `event_stream`:

```python
    memory = MemoryService(db)
```

Replace the body of `event_stream` with this structure:

```python
        try:
            conversation = (
                await db.get(Conversation, request.conversation_id)
                if request.conversation_id
                else await memory.get_or_create_active_conversation(user_id="default")
            )
            if conversation is None:
                conversation = await memory.get_or_create_active_conversation(user_id="default")

            yield f"data: {json.dumps({'event': 'conversation', 'data': {'id': conversation.id}}, ensure_ascii=False)}\n\n"

            await memory.save_message(
                conversation_id=conversation.id,
                role="user",
                content=request.message,
                material_scope=request.material_scope,
                metadata={"mode": "ask"},
            )
            memory_context = await memory.build_memory_context(
                conversation_id=conversation.id,
                user_id="default",
                material_scope=request.material_scope,
            )
            result = await run_orchestrator(
                message=request.message,
                user_id="default",
                material_scope=request.material_scope,
                memory_context=memory_context,
            )
            messages = result.get("messages", [])
            assistant_content = ""
            for msg in messages:
                if hasattr(msg, "content"):
                    content = msg.content
                    if msg.__class__.__name__ == "AIMessage":
                        assistant_content = content
                        for char in content:
                            chunk = json.dumps({"event": "token", "data": char}, ensure_ascii=False)
                            yield f"data: {chunk}\n\n"
                        yield f"data: {json.dumps({'event': 'done', 'data': content}, ensure_ascii=False)}\n\n"
                    else:
                        yield f"data: {json.dumps({'event': 'message', 'data': content}, ensure_ascii=False)}\n\n"
            if assistant_content:
                await memory.save_message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=assistant_content,
                    material_scope=request.material_scope,
                    metadata={"mode": "ask"},
                )
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"
```

- [ ] **Step 5: Run chat tests**

Run:

```bash
cd backend
.venv\Scripts\pytest tests/test_api/test_chat.py tests/test_services/test_memory_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/chat.py backend/app/api/chat.py backend/tests/test_api/test_chat.py
git commit -m "feat: persist chat memory"
```

## Task 5: Orchestrator Memory Context

**Files:**
- Modify: `backend/app/orchestrator/state.py`
- Modify: `backend/app/orchestrator/graph.py`
- Test: `backend/tests/test_orchestrator.py`

- [ ] **Step 1: Add failing orchestrator tests**

Add to `backend/tests/test_orchestrator.py`:

```python
import pytest

from app.orchestrator.graph import run_orchestrator


@pytest.mark.asyncio
async def test_orchestrator_accepts_memory_context():
    result = await run_orchestrator(
        message="继续讲刚才的概念",
        user_id="default",
        memory_context={
            "summary": "用户前面在学习数据库事务隔离级别。",
            "recent_messages": [
                {"role": "user", "content": "什么是幻读？"},
                {"role": "assistant", "content": "幻读是再次查询时出现新增行。"},
            ],
            "learning_profile": {"current_subject": "数据库系统", "weak_concepts": ["幻读"]},
        },
    )

    assert result["memory_context"]["learning_profile"]["current_subject"] == "数据库系统"
    assert result["messages"][-1].content in {
        "QA handling in progress",
        "Quiz generation in progress",
        "Review handling in progress",
    }
```

- [ ] **Step 2: Run orchestrator tests and verify failure**

Run:

```bash
cd backend
.venv\Scripts\pytest tests/test_orchestrator.py -q
```

Expected: FAIL because `AgentState` or graph result does not preserve `memory_context`.

- [ ] **Step 3: Extend graph state**

Modify `backend/app/orchestrator/state.py` to include:

```python
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    messages: list
    intent: str
    user_id: str
    material_scope: list[str] | None
    memory_context: dict[str, Any]
```

Keep any existing state fields by merging them into this `TypedDict`.

- [ ] **Step 4: Preserve memory context in graph input**

Modify `backend/app/orchestrator/graph.py`:

```python
async def run_orchestrator(message: str, user_id: str, **kwargs: Any) -> dict[str, Any]:
    memory_context = kwargs.pop("memory_context", None)
    initial_state: dict[str, Any] = {
        "messages": [HumanMessage(content=message)],
        "intent": "",
        "user_id": user_id,
    }
    if memory_context is not None:
        initial_state["memory_context"] = memory_context
    initial_state.update(kwargs)
    result = await orchestrator.ainvoke(initial_state)
    if memory_context is not None and "memory_context" not in result:
        result["memory_context"] = memory_context
    return result
```

- [ ] **Step 5: Run orchestrator tests**

Run:

```bash
cd backend
.venv\Scripts\pytest tests/test_orchestrator.py tests/test_api/test_chat.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/orchestrator/state.py backend/app/orchestrator/graph.py backend/tests/test_orchestrator.py
git commit -m "feat: pass memory context through orchestrator"
```

## Task 6: Material Metadata And Chunk Rows

**Files:**
- Modify: `backend/app/api/materials.py`
- Modify: `backend/app/schemas/materials.py`
- Test: `backend/tests/test_api/test_materials.py`

- [ ] **Step 1: Add failing material metadata tests**

Add to `backend/tests/test_api/test_materials.py`:

```python
from sqlalchemy import select

from app.db.models import Material, MaterialChunk


@pytest.mark.asyncio
async def test_upload_stores_material_metadata(client_with_db, db_session):
    response = await client_with_db.post(
        "/api/materials",
        files={"file": ("test.pdf", b"fake pdf content", "application/pdf")},
    )
    assert response.status_code == 200
    material_id = _data(response)["id"]

    material = await db_session.get(Material, material_id)
    assert material.storage_path is not None
    assert material.mime_type == "application/pdf"
    assert material.hash is not None


@pytest.mark.asyncio
async def test_delete_material_removes_chunk_rows(client_with_db, db_session):
    upload_resp = await client_with_db.post(
        "/api/materials",
        files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
    )
    material_id = _data(upload_resp)["id"]
    db_session.add(
        MaterialChunk(
            material_id=material_id,
            chunk_id="chunk-delete-test",
            text_preview="preview",
            page_number=1,
            token_count=3,
            embedding_id="chunk-delete-test",
        )
    )
    await db_session.commit()

    response = await client_with_db.delete(f"/api/materials/{material_id}")
    assert response.status_code == 200

    rows = (await db_session.execute(select(MaterialChunk))).scalars().all()
    assert rows == []
```

- [ ] **Step 2: Run material tests and verify failure**

Run:

```bash
cd backend
.venv\Scripts\pytest tests/test_api/test_materials.py -q
```

Expected: FAIL because upload does not fill the new metadata fields.

- [ ] **Step 3: Extend material response schema**

Modify `backend/app/schemas/materials.py`:

```python
    storage_path: str | None = None
    mime_type: str | None = None
    hash: str | None = None
    processed_at: datetime | None = None
    parse_error: str | None = None
```

- [ ] **Step 4: Store upload metadata and chunk rows**

Modify `backend/app/api/materials.py` imports:

```python
import hashlib
import datetime

from app.db.models import FileType, Material, MaterialChunk, ProcessingStatus
```

After reading file content:

```python
    file_hash = hashlib.sha256(content).hexdigest()
```

When creating `Material`:

```python
        storage_path=str(file_path),
        mime_type=file.content_type,
        hash=file_hash,
```

After parsing and indexing chunks:

```python
        chunk_payloads = [asdict(c) for c in result.chunks]
        chunk_ids = await retrieval.index_chunks(user_id="default", chunks=chunk_payloads)
        for chunk_id, chunk in zip(chunk_ids, chunk_payloads, strict=False):
            metadata = chunk.get("metadata", {}) or {}
            db.add(
                MaterialChunk(
                    material_id=material.id,
                    chunk_id=chunk_id,
                    text_preview=(chunk.get("text") or "")[:300],
                    page_number=metadata.get("page"),
                    token_count=len(chunk.get("text") or ""),
                    embedding_id=chunk_id,
                )
            )
        material.processed_at = datetime.datetime.now(datetime.UTC)
```

In the exception block:

```python
        material.parse_error = str(exc)[:500]
```

- [ ] **Step 5: Run material tests**

Run:

```bash
cd backend
.venv\Scripts\pytest tests/test_api/test_materials.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/materials.py backend/app/schemas/materials.py backend/tests/test_api/test_materials.py
git commit -m "feat: track material memory metadata"
```

## Task 7: Frontend Conversation Restore

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/stores/chatStore.ts`
- Modify: `frontend/src/hooks/useChatStream.ts`
- Modify: `frontend/src/app/page.tsx`
- Test: `frontend/src/__tests__/stores/chatStore.test.ts`

- [ ] **Step 1: Add failing chat store tests**

Add to `frontend/src/__tests__/stores/chatStore.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { useChatStore } from "@/stores/chatStore";

describe("chatStore memory state", () => {
  it("stores conversation id and replaces restored messages", () => {
    useChatStore.getState().clearMessages();

    useChatStore.getState().setConversationId(42);
    useChatStore.getState().setMessages([
      {
        id: "m1",
        role: "user",
        content: "什么是幻读？",
        timestamp: 1,
      },
    ]);

    expect(useChatStore.getState().conversationId).toBe(42);
    expect(useChatStore.getState().messages).toHaveLength(1);
    expect(useChatStore.getState().messages[0].content).toBe("什么是幻读？");
  });
});
```

- [ ] **Step 2: Run store test and verify failure**

Run:

```bash
cd frontend
npm test -- src/__tests__/stores/chatStore.test.ts
```

Expected: FAIL because `setConversationId` and `setMessages` do not exist.

- [ ] **Step 3: Extend frontend types**

Modify `frontend/src/types/index.ts`:

```typescript
export interface Conversation {
  id: number;
  title: string;
  summary: string | null;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: number;
  conversation_id: number;
  role: "user" | "assistant" | "system";
  content: string;
  material_scope: string[] | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface LearningProfile {
  current_subject: string | null;
  review_goal: string | null;
  weak_concepts: string[];
  frequent_questions: string[];
  active_materials: string[];
  preferences: Record<string, unknown>;
  updated_at: string;
}
```

- [ ] **Step 4: Extend API client**

Modify `frontend/src/lib/api.ts` imports:

```typescript
import type {
  Conversation,
  ConversationMessage,
  DashboardData,
  LearningProfile,
  Material,
  QuizData,
  ScoreResult,
} from "@/types";
```

Add interfaces:

```typescript
interface ConversationMessagesData {
  conversation_id: number;
  messages: ConversationMessage[];
}
```

Add API methods:

```typescript
  conversations: {
    active: () =>
      fetch(`${API_BASE}/api/conversations/active`).then((r) =>
        unwrap<Conversation>(r),
      ),

    messages: (id: number) =>
      fetch(`${API_BASE}/api/conversations/${id}/messages`).then((r) =>
        unwrap<ConversationMessagesData>(r),
      ),
  },

  memory: {
    profile: () =>
      fetch(`${API_BASE}/api/memory/profile`).then((r) =>
        unwrap<LearningProfile>(r),
      ),
  },
```

- [ ] **Step 5: Extend chat store**

Modify `frontend/src/stores/chatStore.ts`:

```typescript
interface ChatState {
  messages: Message[];
  conversationId: number | null;
  mode: AppMode;
  isStreaming: boolean;
  materialScope: string[];
  addMessage: (msg: Message) => void;
  setMessages: (messages: Message[]) => void;
  setConversationId: (id: number | null) => void;
  setMode: (mode: AppMode) => void;
  setStreaming: (v: boolean) => void;
  setMaterialScope: (scope: string[]) => void;
  clearMessages: () => void;
}
```

Add store fields:

```typescript
  conversationId: null,
  setMessages: (messages) => set({ messages }),
  setConversationId: (id) => set({ conversationId: id }),
```

- [ ] **Step 6: Update chat stream hook**

Modify `frontend/src/hooks/useChatStream.ts`:

```typescript
  const { addMessage, setConversationId, setStreaming, materialScope, conversationId } =
    useChatStore();
```

Include `conversation_id` in request body:

```typescript
            conversation_id: conversationId ?? undefined,
```

Handle conversation stream event:

```typescript
              if (data.event === "conversation") {
                setConversationId(data.data.id);
              } else if (data.event === "token") {
                assistantMsg.content += data.data;
                addMessage({ ...assistantMsg });
              } else if (data.event === "done") {
                assistantMsg.content = data.data || assistantMsg.content;
              }
```

Add `setConversationId` and `conversationId` to the hook dependency array.

- [ ] **Step 7: Restore messages on app load**

Modify `frontend/src/app/page.tsx` with a client-side effect:

```typescript
import { useEffect } from "react";
import { api } from "@/lib/api";
```

Inside the component:

```typescript
  const { setConversationId, setMessages } = useChatStore();

  useEffect(() => {
    let cancelled = false;

    async function loadConversation() {
      const conversation = await api.conversations.active();
      const history = await api.conversations.messages(conversation.id);
      if (cancelled) return;
      setConversationId(conversation.id);
      setMessages(
        history.messages
          .filter((message) => message.role === "user" || message.role === "assistant")
          .map((message) => ({
            id: String(message.id),
            role: message.role,
            content: message.content,
            timestamp: new Date(message.created_at).getTime(),
          })),
      );
    }

    loadConversation().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [setConversationId, setMessages]);
```

- [ ] **Step 8: Run frontend tests and build**

Run:

```bash
cd frontend
npm test -- src/__tests__/stores/chatStore.test.ts
npm run build
```

Expected: store tests PASS and production build PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts frontend/src/stores/chatStore.ts frontend/src/hooks/useChatStream.ts frontend/src/app/page.tsx frontend/src/__tests__/stores/chatStore.test.ts
git commit -m "feat: restore conversation memory in frontend"
```

## Task 8: Verification Pass

**Files:**
- Modify only files required by failures found during this task.
- Test: backend and frontend verification commands below.

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
cd backend
.venv\Scripts\pytest tests/test_db_models.py tests/test_services/test_memory_service.py tests/test_api/test_conversations.py tests/test_api/test_memory.py tests/test_api/test_chat.py tests/test_api/test_materials.py tests/test_orchestrator.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend targeted tests**

Run:

```bash
cd frontend
npm test -- src/__tests__/stores/chatStore.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Manual smoke check**

Start services:

```bash
cd backend
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Check:

```bash
curl http://127.0.0.1:8000/api/conversations/active
curl http://127.0.0.1:8000/api/memory/profile
```

Expected: both responses contain `"success":true`.

- [ ] **Step 5: Finish verification**

If Step 1 through Step 4 pass without code changes, leave the worktree as-is and do not create an empty commit. If a verification command fails, stop this task, inspect the exact failing file from the test output, and create a focused follow-up fix plan for that failure before editing.

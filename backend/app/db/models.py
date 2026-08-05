import datetime
import enum
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _public_id() -> str:
    return uuid.uuid4().hex


JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


def _string_enum(enum_type: type[enum.Enum], name: str) -> SAEnum:
    return SAEnum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class Base(DeclarativeBase):
    pass


class ConversationMode(str, enum.Enum):
    ASK = "ask"
    QUIZ = "quiz"
    REVIEW = "review"


class QuestionType(str, enum.Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    FILL_BLANK = "fill_blank"


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class FileType(str, enum.Enum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    IMAGE = "image"


class Difficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'user')", name="ck_users_role"),
        CheckConstraint("file_limit >= 0", name="ck_users_file_limit"),
        CheckConstraint(
            "storage_limit_bytes >= 0", name="ck_users_storage_limit_bytes"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    email: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    file_limit: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    storage_limit_bytes: Mapped[int] = mapped_column(
        BigInteger, default=2 * 1024 * 1024 * 1024, nullable=False
    )
    disabled_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    conversations = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    materials = relationship(
        "Material", back_populates="user", cascade="all, delete-orphan"
    )
    quiz_sessions = relationship(
        "QuizSession", back_populates="user", cascade="all, delete-orphan"
    )
    answer_records = relationship(
        "AnswerRecord", back_populates="user", cascade="all, delete-orphan"
    )
    mistake_records = relationship(
        "MistakeRecord", back_populates="user", cascade="all, delete-orphan"
    )
    learning_profiles = relationship(
        "LearningProfile", back_populates="user", cascade="all, delete-orphan"
    )
    courses = relationship(
        "Course", back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    account_deletion_jobs = relationship(
        "AccountDeletionJob",
        back_populates="user",
        passive_deletes=True,
    )


class InviteCode(Base):
    __tablename__ = "invite_codes"
    __table_args__ = (
        CheckConstraint("max_uses > 0", name="ck_invite_codes_max_uses"),
        CheckConstraint("use_count >= 0", name="ck_invite_codes_use_count"),
        CheckConstraint(
            "use_count <= max_uses", name="ck_invite_codes_use_count_limit"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    disabled_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_session", "user_id", "session_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replaced_by_token_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    user = relationship("User", back_populates="refresh_tokens")
    replaced_by = relationship(
        "RefreshToken",
        remote_side=[id],
        foreign_keys=[replaced_by_token_id],
        post_update=True,
    )


class AccountDeletionJob(Base):
    __tablename__ = "account_deletion_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_account_deletion_jobs_status",
        ),
        CheckConstraint(
            "attempt_count >= 0", name="ck_account_deletion_jobs_attempt_count"
        ),
        Index(
            "uq_account_deletion_jobs_active_user",
            "user_id",
            unique=True,
        ),
        Index("ix_account_deletion_jobs_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        String(64), default=_public_id, unique=True, nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    user = relationship("User", back_populates="account_deletion_jobs")


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_courses_id_user"),
        UniqueConstraint("user_id", "name", name="uq_courses_user_name"),
        CheckConstraint("length(trim(name)) > 0", name="ck_courses_name_not_blank"),
        Index("ix_courses_user_updated", "user_id", "updated_at"),
        Index(
            "uq_courses_one_default_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_default"),
            sqlite_where=text("is_default = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    user = relationship("User", back_populates="courses")
    exam = relationship(
        "Exam", back_populates="course", cascade="all, delete-orphan", uselist=False
    )
    study_availability = relationship(
        "StudyAvailability",
        back_populates="course",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Exam(Base):
    __tablename__ = "exams"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_exams_user_course"),
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_exams_course_owner",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    exam_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    long_term_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    course = relationship("Course", back_populates="exam")


class StudyAvailability(Base):
    __tablename__ = "study_availabilities"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "course_id", name="uq_study_availability_user_course"
        ),
        CheckConstraint(
            "daily_available_minutes > 0 AND daily_available_minutes <= 1440",
            name="ck_study_availability_daily_minutes",
        ),
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_study_availability_course_owner",
        ),
        Index("ix_study_availability_user_course", "user_id", "course_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    daily_available_minutes: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    course = relationship("Course", back_populates="study_availability")


class LearningProfile(Base):
    __tablename__ = "learning_profiles"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "course_id", name="uq_learning_profiles_user_course"
        ),
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_learning_profiles_course_owner",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    current_subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    review_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    weak_concepts: Mapped[list] = mapped_column(
        JSON_VALUE, default=list, nullable=False
    )
    frequent_questions: Mapped[list] = mapped_column(
        JSON_VALUE, default=list, nullable=False
    )
    active_materials: Mapped[list] = mapped_column(
        JSON_VALUE, default=list, nullable=False
    )
    preferences: Mapped[dict] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    user = relationship("User", back_populates="learning_profiles")
    course = relationship("Course", foreign_keys=[course_id])


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "available_minutes_override IS NULL OR "
            "(available_minutes_override > 0 AND available_minutes_override <= 1440)",
            name="ck_conversations_available_minutes_override",
        ),
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_conversations_course_owner",
        ),
        UniqueConstraint("id", "user_id", "course_id", name="uq_conversations_scope"),
        Index(
            "ix_conversations_user_course_updated",
            "user_id",
            "course_id",
            "updated_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    available_minutes_override: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    title: Mapped[str] = mapped_column(
        String(255), nullable=False, default="New Conversation"
    )
    mode: Mapped[str] = mapped_column(
        _string_enum(ConversationMode, "ck_conversations_mode"),
        default=ConversationMode.ASK,
        nullable=False,
    )
    material_scope: Mapped[list | None] = mapped_column(JSON_VALUE, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_message_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_memory_updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    user = relationship("User", back_populates="conversations")
    course = relationship("Course", foreign_keys=[course_id])
    messages = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "user_id", "course_id"],
            ["conversations.id", "conversations.user_id", "conversations.course_id"],
            ondelete="CASCADE",
            name="fk_conversation_messages_conversation_scope",
        ),
        Index(
            "ix_conversation_messages_user_course",
            "user_id",
            "course_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    role: Mapped[str] = mapped_column(
        _string_enum(MessageRole, "ck_conversation_messages_role"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    material_scope: Mapped[list | None] = mapped_column(JSON_VALUE, nullable=True)
    message_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSON_VALUE, nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    conversation = relationship(
        "Conversation",
        back_populates="messages",
        foreign_keys=[conversation_id, user_id, course_id],
    )


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_materials_course_owner",
        ),
        UniqueConstraint("id", "user_id", "course_id", name="uq_materials_scope"),
        Index("ix_materials_user_status", "user_id", "processing_status"),
        Index("ix_materials_user_created", "user_id", "created_at"),
        Index(
            "ix_materials_user_course_status",
            "user_id",
            "course_id",
            "processing_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(
        _string_enum(FileType, "ck_materials_file_type"), nullable=False
    )
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processing_status: Mapped[str] = mapped_column(
        _string_enum(ProcessingStatus, "ck_materials_processing_status"),
        default=ProcessingStatus.PENDING,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    processed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    user = relationship("User", back_populates="materials")
    course = relationship("Course", foreign_keys=[course_id])
    chunks = relationship(
        "MaterialChunk", back_populates="material", cascade="all, delete-orphan"
    )


class MaterialChunk(Base):
    __tablename__ = "material_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["material_id", "user_id", "course_id"],
            ["materials.id", "materials.user_id", "materials.course_id"],
            ondelete="CASCADE",
            name="fk_material_chunks_material_scope",
        ),
        Index(
            "ix_material_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_material_chunks_user_course", "user_id", "course_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    chunk_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    text_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    lexical_tokens: Mapped[str] = mapped_column(Text, default="", nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    chunk_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON_VALUE, default=dict, nullable=False
    )
    embedding_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    material = relationship(
        "Material",
        back_populates="chunks",
        foreign_keys=[material_id, user_id, course_id],
    )


class QuizSession(Base):
    __tablename__ = "quiz_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_quiz_sessions_course_owner",
        ),
        UniqueConstraint("id", "user_id", "course_id", name="uq_quiz_sessions_scope"),
        Index("ix_quiz_sessions_user_course", "user_id", "course_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    material_scope: Mapped[list | None] = mapped_column(JSON_VALUE, nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_time_seconds: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    difficulty: Mapped[str] = mapped_column(
        _string_enum(Difficulty, "ck_quiz_sessions_difficulty"),
        default=Difficulty.MEDIUM,
        nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    user = relationship("User", back_populates="quiz_sessions")
    course = relationship("Course", foreign_keys=[course_id])
    questions = relationship(
        "Question", back_populates="quiz_session", cascade="all, delete-orphan"
    )


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["quiz_session_id", "user_id", "course_id"],
            ["quiz_sessions.id", "quiz_sessions.user_id", "quiz_sessions.course_id"],
            ondelete="CASCADE",
            name="fk_questions_quiz_scope",
        ),
        UniqueConstraint("id", "user_id", "course_id", name="uq_questions_scope"),
        Index("ix_questions_user_course", "user_id", "course_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quiz_session_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(
        _string_enum(QuestionType, "ck_questions_question_type"), nullable=False
    )
    options: Mapped[list | None] = mapped_column(JSON_VALUE, nullable=True)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str] = mapped_column(
        _string_enum(Difficulty, "ck_questions_difficulty"),
        default=Difficulty.MEDIUM,
        nullable=False,
    )
    topic: Mapped[str | None] = mapped_column(String(100), nullable=True)
    concept: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_chunk_ids: Mapped[list | None] = mapped_column(JSON_VALUE, nullable=True)

    quiz_session = relationship(
        "QuizSession",
        back_populates="questions",
        foreign_keys=[quiz_session_id, user_id, course_id],
    )
    answer_records = relationship(
        "AnswerRecord",
        back_populates="question",
        cascade="all, delete-orphan",
        primaryjoin="Question.id == AnswerRecord.question_id",
        foreign_keys="AnswerRecord.question_id",
    )
    mistake_records = relationship(
        "MistakeRecord",
        back_populates="question",
        cascade="all, delete-orphan",
        primaryjoin="Question.id == MistakeRecord.question_id",
        foreign_keys="MistakeRecord.question_id",
    )


class AnswerRecord(Base):
    __tablename__ = "answer_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_answer_records_course_owner",
        ),
        ForeignKeyConstraint(
            ["question_id", "user_id", "course_id"],
            ["questions.id", "questions.user_id", "questions.course_id"],
            ondelete="CASCADE",
            name="fk_answer_records_question_scope",
        ),
        ForeignKeyConstraint(
            ["quiz_session_id", "user_id", "course_id"],
            ["quiz_sessions.id", "quiz_sessions.user_id", "quiz_sessions.course_id"],
            ondelete="CASCADE",
            name="fk_answer_records_quiz_scope",
        ),
        Index("ix_answer_records_user_course", "user_id", "course_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    quiz_session_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    student_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    time_spent_seconds: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    question = relationship(
        "Question",
        back_populates="answer_records",
        primaryjoin="Question.id == AnswerRecord.question_id",
        foreign_keys=[question_id],
    )
    user = relationship("User", back_populates="answer_records")
    course = relationship("Course", foreign_keys=[course_id])


class MistakeRecord(Base):
    __tablename__ = "mistake_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_mistake_records_course_owner",
        ),
        ForeignKeyConstraint(
            ["question_id", "user_id", "course_id"],
            ["questions.id", "questions.user_id", "questions.course_id"],
            ondelete="CASCADE",
            name="fk_mistake_records_question_scope",
        ),
        Index(
            "ix_mistakes_user_status_review",
            "user_id",
            "status",
            "next_review_at",
        ),
        Index("ix_mistakes_user_concept", "user_id", "concept"),
        Index(
            "ix_mistakes_user_course_review",
            "user_id",
            "course_id",
            "next_review_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        String(128), default=_public_id, nullable=False, unique=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    question_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    source_question_id: Mapped[str] = mapped_column(
        String(128), default="", nullable=False, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    question_type: Mapped[str] = mapped_column(
        String(32), default=QuestionType.MULTIPLE_CHOICE.value, nullable=False
    )
    concept: Mapped[str | None] = mapped_column(String(100), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(100), nullable=True)
    wrong_answer: Mapped[str] = mapped_column(Text, nullable=False)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_chunk_ids: Mapped[list] = mapped_column(
        JSON_VALUE, default=list, nullable=False
    )
    source_material: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="unreviewed", nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_wrong_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    correction_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    mastered_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_history: Mapped[list] = mapped_column(
        JSON_VALUE, default=list, nullable=False
    )
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5, nullable=False)
    next_review_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user = relationship("User", back_populates="mistake_records")
    course = relationship("Course", foreign_keys=[course_id])
    question = relationship(
        "Question",
        back_populates="mistake_records",
        primaryjoin="Question.id == MistakeRecord.question_id",
        foreign_keys=[question_id],
    )


class Concept(Base):
    __tablename__ = "concepts"
    __table_args__ = (
        UniqueConstraint("id", "user_id", "course_id", name="uq_concepts_scope"),
        UniqueConstraint(
            "user_id", "course_id", "name", name="uq_concepts_course_name"
        ),
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_concepts_course_owner",
        ),
        Index("ix_concepts_user_course_topic", "user_id", "course_id", "topic"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    course = relationship("Course", foreign_keys=[course_id])
    masteries = relationship(
        "ConceptMastery", back_populates="concept", cascade="all, delete-orphan"
    )

    prerequisites = relationship(
        "ConceptDependency",
        foreign_keys=(
            "[ConceptDependency.dependent_id, ConceptDependency.user_id, "
            "ConceptDependency.course_id]"
        ),
        back_populates="dependent",
        cascade="all, delete-orphan",
        overlaps="dependents,prerequisite",
    )
    dependents = relationship(
        "ConceptDependency",
        foreign_keys=(
            "[ConceptDependency.prerequisite_id, ConceptDependency.user_id, "
            "ConceptDependency.course_id]"
        ),
        back_populates="prerequisite",
        cascade="all, delete-orphan",
        overlaps="dependent,prerequisites",
    )


class ConceptDependency(Base):
    __tablename__ = "concept_dependencies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["prerequisite_id", "user_id", "course_id"],
            ["concepts.id", "concepts.user_id", "concepts.course_id"],
            ondelete="CASCADE",
            name="fk_concept_dependencies_prerequisite_scope",
        ),
        ForeignKeyConstraint(
            ["dependent_id", "user_id", "course_id"],
            ["concepts.id", "concepts.user_id", "concepts.course_id"],
            ondelete="CASCADE",
            name="fk_concept_dependencies_dependent_scope",
        ),
        CheckConstraint(
            "prerequisite_id <> dependent_id",
            name="ck_concept_dependencies_distinct_nodes",
        ),
        Index(
            "ix_concept_dependencies_user_course",
            "user_id",
            "course_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    prerequisite_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    dependent_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    prerequisite = relationship(
        "Concept",
        foreign_keys=[prerequisite_id, user_id, course_id],
        back_populates="dependents",
        overlaps="dependent,prerequisites",
    )
    dependent = relationship(
        "Concept",
        foreign_keys=[dependent_id, user_id, course_id],
        back_populates="prerequisites",
        overlaps="dependents,prerequisite",
    )


class ConceptMastery(Base):
    __tablename__ = "concept_masteries"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "course_id", "concept_id", name="uq_concept_mastery_scope"
        ),
        CheckConstraint(
            "mastery_score >= 0 AND mastery_score <= 1",
            name="ck_concept_mastery_score",
        ),
        ForeignKeyConstraint(
            ["concept_id", "user_id", "course_id"],
            ["concepts.id", "concepts.user_id", "concepts.course_id"],
            ondelete="CASCADE",
            name="fk_concept_mastery_concept_scope",
        ),
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_concept_mastery_course_owner",
        ),
        Index(
            "ix_concept_mastery_user_course",
            "user_id",
            "course_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    concept_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    concept = relationship(
        "Concept",
        foreign_keys=[concept_id, user_id, course_id],
        back_populates="masteries",
        overlaps="course,concept_masteries",
    )

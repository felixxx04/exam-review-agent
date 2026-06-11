# Final Exam Review Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-agent final exam review system with RAG Q&A, auto-quiz generation, and mistake tracking, deployable as a portfolio project.

**Architecture:** Three-layer multi-agent system (Coordinator → Functional Agents → Specialists) orchestrated by LangGraph StateGraph. FastAPI backend with hybrid RAG retrieval, Next.js frontend with streaming chat UI.

**Tech Stack:** Python/FastAPI, LangGraph, LangChain, ChromaDB, SQLAlchemy, ARQ/Redis, Next.js App Router, TailwindCSS, Zustand, DeepSeek/MiniMax/GLM APIs

**Design Spec:** `docs/superpowers/specs/2026-06-10-final-exam-review-agent-design.md`

---

## File Structure

### Backend

```
backend/
├── pyproject.toml
├── .env.example
├── alembic.ini
├── migrations/
│   └── versions/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   └── middleware.py
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── state.py
│   │   └── router.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── rag_agent.py
│   │   ├── quiz_agent.py
│   │   └── tracker_agent.py
│   ├── specialists/
│   │   ├── __init__.py
│   │   ├── quiz_generator.py
│   │   ├── paper_analyzer.py
│   │   └── mistake_summarizer.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── llm_service.py
│   │   ├── llm_providers/
│   │   │   ├── __init__.py
│   │   │   ├── deepseek.py
│   │   │   ├── minimax.py
│   │   │   └── glm.py
│   │   ├── embedding_service.py
│   │   ├── retrieval_service.py
│   │   ├── parser_service.py
│   │   └── scheduler_service.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── vector_store.py
│   │   └── models.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── chat.py
│   │   ├── materials.py
│   │   ├── quiz.py
│   │   └── review.py
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── worker.py
│   │   └── parse_material.py
│   └── api/
│       ├── __init__.py
│       ├── chat.py
│       ├── materials.py
│       ├── quiz.py
│       └── review.py
└── tests/
    ├── conftest.py
    ├── test_llm_service.py
    ├── test_retrieval_service.py
    ├── test_parser_service.py
    ├── test_rag_agent.py
    ├── test_quiz_agent.py
    ├── test_tracker_agent.py
    ├── test_orchestrator.py
    └── test_api/
        ├── test_chat.py
        ├── test_materials.py
        └── test_quiz.py
```

### Frontend

```
frontend/
├── package.json
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── api/
│   │       └── chat/
│   │           └── route.ts
│   ├── components/
│   │   ├── ChatLayout.tsx
│   │   ├── Header.tsx
│   │   ├── ModeSwitch.tsx
│   │   ├── MaterialsBar.tsx
│   │   ├── FileChip.tsx
│   │   ├── DropZone.tsx
│   │   ├── MessageList.tsx
│   │   ├── StreamMessage.tsx
│   │   ├── QuizCard.tsx
│   │   ├── DashboardCard.tsx
│   │   ├── DefinitionCard.tsx
│   │   ├── ComparisonTable.tsx
│   │   └── ChatInput.tsx
│   ├── hooks/
│   │   ├── useChatStream.ts
│   │   └── useMaterials.ts
│   ├── stores/
│   │   ├── chatStore.ts
│   │   └── quizStore.ts
│   ├── lib/
│   │   └── api.ts
│   └── types/
│       └── index.ts
└── __tests__/
    ├── QuizCard.test.tsx
    ├── MessageList.test.tsx
    └── DashboardCard.test.tsx
```

---

## MVP — Phase 1: Project Scaffolding & Shared Services (Week 1)

### Task 1: Initialize Backend Project

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/app/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/exceptions.py`
- Create: `backend/app/core/middleware.py`
- Create: `backend/app/core/__init__.py`
- Test: `backend/tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml with dependencies**

```toml
[project]
name = "exam-review-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn>=0.34.0",
    "sqlalchemy>=2.0.0",
    "alembic>=1.14.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.7.0",
    "langchain>=0.3.0",
    "langchain-core>=0.3.0",
    "langgraph>=0.2.0",
    "chromadb>=0.5.0",
    "arq>=0.26.0",
    "redis>=5.0.0",
    "python-jose>=3.3.0",
    "passlib>=1.7.0",
    "python-multipart>=0.0.18",
    "httpx>=0.28.0",
    "pymupdf>=1.25.0",
    "python-docx>=1.1.0",
    "python-pptx>=1.0.0",
    "pillow>=11.0.0",
    "rank-bm25>=0.2.2",
    "sentence-transformers>=3.0.0",
    "python-magic>=0.4.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=6.0.0",
    "httpx>=0.28.0",
]
```

- [ ] **Step 2: Create .env.example**

```
DATABASE_URL=sqlite+aiosqlite:///./dev.db
REDIS_URL=redis://localhost:6379
CHROMA_PERSIST_DIR=./chroma_data

DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://api.minimax.chat
GLM_API_KEY=
GLM_BASE_URL=https://open.bigmodel.cn/api/paas

DEFAULT_LLM_PROVIDER=deepseek
JWT_SECRET=change-me-in-production

MAX_UPLOAD_SIZE_MB=50
```

- [ ] **Step 3: Create core/config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./dev.db"
    redis_url: str = "redis://localhost:6379"
    chroma_persist_dir: str = "./chroma_data"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimax.chat"
    glm_api_key: str = ""
    glm_base_url: str = "https://open.bigmodel.cn/api/paas"

    default_llm_provider: str = "deepseek"
    jwt_secret: str = "change-me-in-production"
    max_upload_size_mb: int = 50

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

- [ ] **Step 4: Create core/exceptions.py with custom exception types**

```python
class AppException(Exception):
    def __init__(self, message: str, code: str = "APP_ERROR"):
        self.message = message
        self.code = code

class InsufficientMaterialError(AppException):
    def __init__(self, message: str = "上传的资料中未找到相关内容"):
        super().__init__(message, "INSUFFICIENT_MATERIAL")

class LLMProviderError(AppException):
    def __init__(self, provider: str, message: str = ""):
        super().__init__(f"LLM provider {provider} error: {message}", "LLM_PROVIDER_ERROR")

class FileParsingError(AppException):
    def __init__(self, filename: str, message: str = ""):
        super().__init__(f"Failed to parse {filename}: {message}", "FILE_PARSING_ERROR")

class RateLimitExceededError(AppException):
    def __init__(self):
        super().__init__("Rate limit exceeded", "RATE_LIMIT_EXCEEDED")
```

- [ ] **Step 5: Create main.py with FastAPI app**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.middleware import RateLimitMiddleware

app = FastAPI(title="Exam Review Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

@app.get("/api/health")
async def health():
    return {"status": "ok", "default_provider": settings.default_llm_provider}
```

- [ ] **Step 6: Create conftest.py with test fixtures**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

- [ ] **Step 7: Run health check test**

```python
import pytest

@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
```

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: initialize backend project with FastAPI, config, and exceptions"
```

---

### Task 2: Database Models & Migrations

**Files:**
- Create: `backend/app/db/database.py`
- Create: `backend/app/db/models.py`
- Create: `backend/alembic.ini`
- Test: `backend/tests/test_db_models.py`

- [ ] **Step 1: Write failing test for User model creation**

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.db.models import User, Base

@pytest.mark.asyncio
async def test_create_user():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        user = User(email="test@example.com", hashed_password="xxx", display_name="Test")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        assert user.id is not None
        assert user.email == "test@example.com"
```

- [ ] **Step 2: Implement models.py with all data models**

Define: User, Conversation, Material, QuizSession, Question, AnswerRecord, MistakeRecord, Concept, ConceptDependency with all fields and indices from the spec. Use SQLAlchemy 2.0 mapped_column style.

- [ ] **Step 3: Implement database.py with async session factory**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings

engine = create_async_engine(settings.database_url)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 4: Run test, verify pass, commit**

```bash
pytest tests/test_db_models.py -v
git add backend/app/db/ backend/tests/test_db_models.py
git commit -m "feat: add SQLAlchemy models and async database session"
```

---

### Task 3: Multi-Model LLM Service

**Files:**
- Create: `backend/app/services/llm_service.py`
- Create: `backend/app/services/llm_providers/__init__.py`
- Create: `backend/app/services/llm_providers/deepseek.py`
- Create: `backend/app/services/llm_providers/minimax.py`
- Create: `backend/app/services/llm_providers/glm.py`
- Test: `backend/tests/test_llm_service.py`

- [ ] **Step 1: Write failing test for LLM service invoke with fallback**

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.services.llm_service import LLMService
from app.core.exceptions import LLMProviderError

@pytest.mark.asyncio
async def test_llm_invoke_with_fallback():
    service = LLMService(default_provider="deepseek")
    with patch.object(service, "_invoke_provider") as mock_invoke:
        mock_invoke.side_effect = [
            LLMProviderError("deepseek", "rate limit"),
            AsyncMock(return_value="GLM response")(),
        ]
        result = await service.invoke("test prompt", fallback_chain=["glm"])
        assert result == "GLM response"
```

- [ ] **Step 2: Implement LLMService with exponential backoff, circuit breaker, fallback chain**

Key features: unified `invoke()` method, per-provider circuit breaker, 3 retries with jitter, fallback chain DeepSeek→GLM→MiniMax, latency/token logging.

- [ ] **Step 3: Implement provider adapters (deepseek.py, minimax.py, glm.py)**

Each provider: `async def invoke(self, messages, **kwargs) -> str` using httpx to call the provider's OpenAI-compatible API.

- [ ] **Step 4: Run tests, verify pass, commit**

---

### Task 4: Embedding & Hybrid Retrieval Service

**Files:**
- Create: `backend/app/services/embedding_service.py`
- Create: `backend/app/services/retrieval_service.py`
- Create: `backend/app/db/vector_store.py`
- Test: `backend/tests/test_retrieval_service.py`

- [ ] **Step 1: Write failing test for hybrid retrieval**

```python
import pytest
from app.services.retrieval_service import RetrievalService

@pytest.mark.asyncio
async def test_hybrid_search_returns_ranked_results():
    service = RetrievalService()
    # Pre-index test documents
    await service.index_chunks("test-user", [
        {"text": "薛定谔方程描述量子态随时间的演化", "metadata": {"source": "quantum.pdf", "page": 23}},
        {"text": "矩阵的特征值是满足det(A-λI)=0的λ", "metadata": {"source": "linalg.pdf", "page": 45}},
    ])
    results = await service.search("test-user", "什么是薛定谔方程", top_k=2)
    assert len(results) >= 1
    assert "薛定谔" in results[0].text
```

- [ ] **Step 2: Implement vector_store.py (ChromaDB wrapper)**

Collection-per-user pattern, add/search/delete with metadata filtering.

- [ ] **Step 3: Implement embedding_service.py using bge-large-zh**

- [ ] **Step 4: Implement retrieval_service.py with BM25 + dense + rerank + quality gate**

- [ ] **Step 5: Run tests, verify pass, commit**

---

### Task 5: File Parser Service

**Files:**
- Create: `backend/app/services/parser_service.py`
- Create: `backend/app/specialists/paper_analyzer.py`
- Create: `backend/app/tasks/worker.py`
- Create: `backend/app/tasks/parse_material.py`
- Test: `backend/tests/test_parser_service.py`

- [ ] **Step 1: Write failing test for PDF parsing**

```python
import pytest
from app.services.parser_service import ParserService

@pytest.mark.asyncio
async def test_parse_pdf_extracts_text_and_metadata():
    service = ParserService()
    result = await service.parse("tests/fixtures/sample.pdf")
    assert len(result.chunks) > 0
    assert result.chunks[0].metadata["source"] == "sample.pdf"
    assert "page" in result.chunks[0].metadata
```

- [ ] **Step 2: Implement ParserService with PDF (PyMuPDF), Word (python-docx), PPT (python-pptx)**

- [ ] **Step 3: Implement ARQ async task for background parsing**

- [ ] **Step 4: Run tests, verify pass, commit**

---

## MVP — Phase 2: Agents & Orchestrator (Week 2)

### Task 6: Orchestrator (LangGraph StateGraph)

**Files:**
- Create: `backend/app/orchestrator/state.py`
- Create: `backend/app/orchestrator/router.py`
- Create: `backend/app/orchestrator/graph.py`
- Test: `backend/tests/test_orchestrator.py`

- [ ] **Step 1: Write failing test for intent routing**

```python
import pytest
from app.orchestrator.router import classify_intent

def test_classify_quiz_intent():
    assert classify_intent("基于第三章出5道选择题") == "quiz"

def test_classify_qa_intent():
    assert classify_intent("解释一下薛定谔方程") == "qa"

def test_classify_review_intent():
    assert classify_intent("查看我的错题") == "review"
```

- [ ] **Step 2: Implement router.py with keyword-based intent classification**

INTENT_KEYWORDS dict with Chinese + English keywords for quiz, qa, review intents.

- [ ] **Step 3: Implement state.py with TypedDict for shared state**

```python
from typing import TypedDict, Annotated
from langgraph.graph import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    user_id: str
    material_scope: list[str] | None
    active_session: dict | None
```

- [ ] **Step 4: Implement graph.py as LangGraph StateGraph**

Nodes: route_intent, handle_qa, handle_quiz, handle_review. Conditional edges based on intent.

- [ ] **Step 5: Run tests, verify pass, commit**

---

### Task 7: RAG Agent

**Files:**
- Create: `backend/app/agents/rag_agent.py`
- Test: `backend/tests/test_rag_agent.py`

- [ ] **Step 1: Write failing test for RAG agent answer generation**

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.agents.rag_agent import RAGAgent

@pytest.mark.asyncio
async def test_rag_agent_returns_answer_with_citations():
    agent = RAGAgent(llm_service=AsyncMock(), retrieval_service=AsyncMock())
    agent.retrieval_service.search = AsyncMock(return_value=[
        AsyncMock(text="薛定谔方程: iℏ∂ψ/∂t = Ĥψ", metadata={"source": "quantum.pdf", "page": 23}),
    ])
    agent.llm_service.invoke = AsyncMock(return_value="薛定谔方程描述量子态随时间演化[iℏ∂ψ/∂t = Ĥψ]【来源: quantum.pdf P.23】")
    result = await agent.answer("什么是薛定谔方程", user_id="test")
    assert "薛定谔" in result.text
    assert len(result.citations) >= 1
```

- [ ] **Step 2: Implement RAGAgent with retrieval → prompt assembly → LLM → citation extraction**

- [ ] **Step 3: Add material scope filtering (user can specify which materials to use)**

- [ ] **Step 4: Run tests, verify pass, commit**

---

### Task 8: Quiz Agent + QuizGenerator Specialist

**Files:**
- Create: `backend/app/agents/quiz_agent.py`
- Create: `backend/app/specialists/quiz_generator.py`
- Create: `backend/app/schemas/quiz.py`
- Test: `backend/tests/test_quiz_agent.py`

- [ ] **Step 1: Write failing test for quiz generation with source citations**

```python
import pytest
from unittest.mock import AsyncMock
from app.specialists.quiz_generator import QuizGenerator

@pytest.mark.asyncio
async def test_quiz_generator_produces_questions_with_source_ids():
    generator = QuizGenerator(llm_service=AsyncMock())
    generator.llm_service.invoke = AsyncMock(return_value='[{"question":"以下哪个是薛定谔方程?","options":["A. E=mc²","B. iℏ∂ψ/∂t=Ĥψ","C. F=ma","D. ∇²φ=ρ/ε₀"],"correct":"B","explanation":"薛定谔方程是量子力学基本方程","source_chunk_ids":["chunk-1"]}]')
    questions = await generator.generate(
        chunks=[AsyncMock(id="chunk-1", text="薛定谔方程相关内容")],
        difficulty=0.5, count=1
    )
    assert len(questions) == 1
    assert questions[0].source_chunk_ids == ["chunk-1"]
    assert questions[0].correct == "B"
```

- [ ] **Step 2: Implement QuizGenerator with difficulty adjustment and structured prompt**

- [ ] **Step 3: Implement QuizAgent (calls RetrievalService → QuizGenerator → returns questions)**

- [ ] **Step 4: Add Pydantic schemas for quiz request/response**

- [ ] **Step 5: Run tests, verify pass, commit**

---

### Task 9: Tracker Agent + MistakeSummarizer Specialist

**Files:**
- Create: `backend/app/agents/tracker_agent.py`
- Create: `backend/app/specialists/mistake_summarizer.py`
- Test: `backend/tests/test_tracker_agent.py`

- [ ] **Step 1: Write failing test for scoring and mistake recording**

```python
import pytest
from app.agents.tracker_agent import TrackerAgent

@pytest.mark.asyncio
async def test_tracker_scores_mc_and_records_mistake():
    tracker = TrackerAgent(db=AsyncMock())
    result = await tracker.score_answer(
        question_id="q1",
        correct_answer="B",
        student_answer="A",
        question_type="multiple_choice"
    )
    assert result.is_correct is False
    assert result.mistake_recorded is True
```

- [ ] **Step 2: Implement TrackerAgent with scoring (MC exact match, fill-blank normalized match)**

- [ ] **Step 3: Implement mistake recording with concept tagging and two-level knowledge model**

- [ ] **Step 4: Implement MistakeSummarizer with hybrid summary update (full rewrite <5, incremental >=5)**

- [ ] **Step 5: Run tests, verify pass, commit**

---

## MVP — Phase 3: API Endpoints (Week 3)

### Task 10: Materials API (Upload, List, Delete, Reprocess)

**Files:**
- Create: `backend/app/api/materials.py`
- Create: `backend/app/schemas/materials.py`
- Test: `backend/tests/test_api/test_materials.py`

- [ ] **Step 1: Write failing test for material upload**

```python
import pytest

@pytest.mark.asyncio
async def test_upload_material_returns_pending_status(client):
    response = await client.post("/api/materials", files={"file": ("test.pdf", b"fake pdf content", "application/pdf")})
    assert response.status_code == 200
    data = response.json()
    assert data["processing_status"] == "pending"
    assert data["filename"] == "test.pdf"
```

- [ ] **Step 2: Implement upload endpoint with MIME validation, UUID filename, 50MB cap**

- [ ] **Step 3: Implement list, delete (cascade chunk cleanup), reprocess endpoints**

- [ ] **Step 4: Add Pydantic schemas for materials**

- [ ] **Step 5: Run tests, verify pass, commit**

---

### Task 11: Chat API (SSE Streaming)

**Files:**
- Create: `backend/app/api/chat.py`
- Create: `backend/app/schemas/chat.py`
- Test: `backend/tests/test_api/test_chat.py`

- [ ] **Step 1: Write failing test for SSE chat endpoint**

```python
import pytest

@pytest.mark.asyncio
async def test_chat_returns_sse_stream(client):
    response = await client.post("/api/chat", json={"message": "什么是量子力学", "user_id": "test"})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
```

- [ ] **Step 2: Implement SSE streaming endpoint that invokes orchestrator and streams tokens**

- [ ] **Step 3: Add chat schemas (ChatRequest, SSEEvent types)**

- [ ] **Step 4: Run tests, verify pass, commit**

---

### Task 12: Quiz & Review API

**Files:**
- Create: `backend/app/api/quiz.py`
- Create: `backend/app/api/review.py`
- Create: `backend/app/schemas/review.py`
- Test: `backend/tests/test_api/test_quiz.py`

- [ ] **Step 1: Implement quiz submit endpoint (POST /api/quiz/submit → scoring + mistake recording)**

- [ ] **Step 2: Implement quiz sessions list endpoint (GET /api/quiz/sessions)**

- [ ] **Step 3: Implement review endpoints (GET weak-points, GET mistakes)**

- [ ] **Step 4: Add Pydantic schemas for review**

- [ ] **Step 5: Run tests, verify pass, commit**

---

### Task 13: Auth & Security Middleware

**Files:**
- Modify: `backend/app/core/middleware.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Implement JWT-based auth dependency (get_current_user)**

- [ ] **Step 2: Implement rate limiting middleware (per-user on /api/chat and /api/materials POST)**

- [ ] **Step 3: Implement prompt injection guard (delimit user input, lightweight classifier)**

- [ ] **Step 4: Add auth dependencies to protected endpoints**

- [ ] **Step 5: Run tests, verify pass, commit**

---

## MVP — Phase 4: Frontend (Week 4)

### Task 14: Initialize Frontend Project

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/next.config.ts`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/src/types/index.ts`

- [ ] **Step 1: Create Next.js project with App Router + TailwindCSS + all dependencies**

```bash
cd frontend && npx create-next-app@latest . --typescript --tailwind --app --src-dir
npm install zustand @microsoft/fetch-event-source @tanstack/react-virtual recharts react-markdown rehype-katex react-dropzone @radix-ui/react-radio-group lucide-react
```

- [ ] **Step 2: Create TypeScript types matching backend schemas**

```typescript
export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  quiz?: QuizData;
  dashboard?: DashboardData;
  timestamp: number;
}

export interface Citation {
  source: string;
  page: number;
  chunk_id: string;
}

export interface QuizQuestion {
  id: string;
  question: string;
  question_type: "multiple_choice" | "fill_blank";
  options?: string[];
  difficulty: number;
  topic: string;
  source_chunk_ids: string[];
}

export interface Material {
  id: string;
  filename: string;
  page_count: number;
  processing_status: "pending" | "processing" | "ready" | "failed";
  created_at: string;
}

export interface WeakConcept {
  concept: string;
  topic: string;
  accuracy: number;
  attempt_count: number;
}
```

- [ ] **Step 3: Create Zustand stores (chatStore, quizStore)**

```typescript
import { create } from "zustand";

interface ChatState {
  messages: Message[];
  mode: "ask" | "quiz" | "review";
  isStreaming: boolean;
  addMessage: (msg: Message) => void;
  setMode: (mode: "ask" | "quiz" | "review") => void;
  setStreaming: (v: boolean) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  mode: "ask",
  isStreaming: false,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setMode: (mode) => set({ mode }),
  setStreaming: (v) => set({ isStreaming: v }),
}));
```

- [ ] **Step 4: Commit**

---

### Task 15: Frontend — Impeccable Shape Phase

This task runs the Impeccable shape workflow for each major surface.

- [ ] **Step 1: Run `/impeccable shape` for ChatLayout + Header + ChatInput**

Answer discovery questions: primary action = ask questions, user mental state = focused/exam-anxious, anchor references = Perplexity/Notion AI/ChatGPT, color strategy = Restrained, scope = production-ready.

- [ ] **Step 2: Run `/impeccable shape` for MaterialsBar + FileChip + DropZone**

Discovery: ranges = 0-20 files, empty state = "拖拽或点击上传复习资料", processing states with indicators.

- [ ] **Step 3: Run `/impeccable shape` for QuizCard**

Discovery: states = unanswered/selected/submitted-correct/submitted-wrong/explanation-expanded, feedback timing = 150ms, anchor = Notion AI inline blocks.

- [ ] **Step 4: Run `/impeccable shape` for DashboardCard**

Discovery: data ranges = 0-50 concepts, 0-100% accuracy, cold start = prompt diagnostic quiz.

- [ ] **Step 5: Save confirmed briefs, commit**

---

### Task 16: Frontend — Impeccable Craft Phase

Build each surface following shape briefs through the craft flow.

- [ ] **Step 1: Run `/impeccable craft` for ChatLayout + Header + ChatInput**

Build streaming chat shell with mode switch, SSE integration via useChatStream hook, Zustand state.

- [ ] **Step 2: Run `/impeccable craft` for MaterialsBar + FileChip + DropZone**

Build file upload with react-dropzone, chips with processing status indicators, async parsing feedback.

- [ ] **Step 3: Run `/impeccable craft` for QuizCard + progress bar**

Build interactive quiz cards with @radix-ui/react-radio-group, answer submission, floating progress bar.

- [ ] **Step 4: Run `/impeccable craft` for DashboardCard**

Build weak points dashboard with recharts donut chart, ranked list, re-quiz action.

- [ ] **Step 5: Run `/impeccable craft` for DefinitionCard + ComparisonTable**

Build structured output components for RAG agent responses.

- [ ] **Step 6: Implement useChatStream hook with @microsoft/fetch-event-source**

SSE streaming with reconnect, Last-Event-ID, token-by-token rendering.

- [ ] **Step 7: Implement MessageList with @tanstack/react-virtual**

Virtualized long chat histories for performance.

- [ ] **Step 8: Connect frontend to backend API**

Wire up all components to FastAPI endpoints via the api.ts client.

- [ ] **Step 9: Commit each surface as it passes visual inspection**

---

### Task 17: Frontend — Taste Skill + Critique + Polish

Quality gate after each surface is crafted.

- [ ] **Step 1: Run `design-taste-frontend` on ChatLayout**

Audit for AI slop, verify intentional hierarchy, check spacing rhythm.

- [ ] **Step 2: Run `design-taste-frontend` on QuizCard**

Verify quiz cards look product-specific, not template-like.

- [ ] **Step 3: Run `design-taste-frontend` on DashboardCard**

Ensure dashboard reads as intentional data viz, not generic chart.

- [ ] **Step 4: Run `/impeccable critique` on all surfaces**

Dual assessment: design review (heuristics, cognitive load, slop) + detector scan (contrast, anti-patterns).

- [ ] **Step 5: Run `/impeccable polish` addressing critique findings**

- [ ] **Step 6: Run `/impeccable audit` for a11y, perf, responsive checks**

- [ ] **Step 7: Run `/impeccable onboard` for empty states and first-run experience**

- [ ] **Step 8: Commit polished frontend**

---

## v1.1 — Enhancements (Weeks 5-6)

### Task 18: Adaptive Difficulty

**Files:**
- Modify: `backend/app/agents/tracker_agent.py`
- Modify: `backend/app/specialists/quiz_generator.py`

- [ ] **Step 1: Write failing test for adaptive difficulty signal**

```python
@pytest.mark.asyncio
async def test_tracker_sends_difficulty_signal():
    tracker = TrackerAgent(db=AsyncMock())
    # After 3 wrong answers on "特征值", difficulty should drop to 0.2
    for _ in range(3):
        await tracker.score_answer("q1", "B", "A", "multiple_choice", concept="特征值")
    signal = await tracker.get_adaptive_difficulty("特征值")
    assert signal <= 0.3
```

- [ ] **Step 2: Implement adaptive difficulty logic in TrackerAgent**

- [ ] **Step 3: Wire QuizGenerator to use difficulty signal from Tracker**

- [ ] **Step 4: Run tests, verify pass, commit**

---

### Task 19: Wrong Answer Explanation with Source Citations

**Files:**
- Modify: `backend/app/agents/tracker_agent.py`

- [ ] **Step 1: Implement explanation generation after wrong answer**

Call LLM with source chunks to explain why correct answer is right and why student's answer is wrong, with citations.

- [ ] **Step 2: Update frontend QuizCard to show explanation with citations**

- [ ] **Step 3: Run tests, verify pass, commit**

---

### Task 20: Weak Points Dashboard Data

**Files:**
- Modify: `backend/app/api/review.py`
- Modify: `frontend/src/components/DashboardCard.tsx`

- [ ] **Step 1: Implement GET /api/review/weak-points with actual data aggregation**

- [ ] **Step 2: Update DashboardCard to show real data from backend**

- [ ] **Step 3: Add re-quiz action that triggers Quiz Agent on weak concepts**

- [ ] **Step 4: Run tests, verify pass, commit**

---

### Task 21: Study Plan Generation

**Files:**
- Modify: `backend/app/agents/tracker_agent.py`
- Modify: `backend/app/api/review.py`

- [ ] **Step 1: Implement POST /api/review/study-plan**

Generate a day-by-day study plan based on exam date and weak concepts using LLM.

- [ ] **Step 2: Add study plan card to frontend**

- [ ] **Step 3: Run tests, verify pass, commit**

---

### Task 22: Quiz Progress Tracking

**Files:**
- Modify: `frontend/src/components/QuizCard.tsx`
- Modify: `frontend/src/stores/quizStore.ts`

- [ ] **Step 1: Implement quiz progress tracking in Zustand store**

Track current quiz session: questions answered, correct count, elapsed time.

- [ ] **Step 2: Add floating progress bar with real-time updates**

- [ ] **Step 3: Add quiz summary card on completion (score, time, weak concepts)**

- [ ] **Step 4: Commit**

---

## v1.2 — Nice-to-Have (Post v1.1)

### Task 23: Spaced Repetition Scheduler

- [ ] **Step 1: Implement SM-2 algorithm variant in scheduler_service.py**

- [ ] **Step 2: Add next_review_at scheduling after wrong answers**

- [ ] **Step 3: Add "Review in X days?" prompt in frontend after wrong answers**

- [ ] **Step 4: Run tests, verify pass, commit**

---

### Task 24: Concept Coverage Report

- [ ] **Step 1: Implement concept coverage calculation (which topics quizzed, which have gaps)**

- [ ] **Step 2: Add coverage report endpoint and frontend card**

- [ ] **Step 3: Commit**

---

### Task 25: Evaluation Harness

- [ ] **Step 1: Create gold Q&A pairs for smoke testing**

- [ ] **Step 2: Implement evaluation script that runs pipeline against gold pairs**

- [ ] **Step 3: Add to CI or manual run script**

- [ ] **Step 4: Commit**

---

## Self-Review

- [ ] **Spec coverage check:** Every spec section maps to at least one task
- [ ] **Placeholder scan:** No TBD/TODO/fill-in-details in any step
- [ ] **Type consistency:** All type names, method signatures, and property names are consistent across tasks

# Final Exam Review Agent — Design Spec

**Date:** 2026-06-10
**Status:** Final
**Timeline:** 1-2 months
**Purpose:** Portfolio project for AI Agent job application; multi-agent study assistant for college students

---

## 1. Overview

A multi-agent system where students upload study materials (PDF/Word/PPT/images), ask questions grounded in those materials, take auto-generated quizzes, and track mistakes with adaptive review. Three specialized agents collaborate through a LangGraph StateGraph orchestrator.

### Target Users

College students preparing for final exams. Multi-user support required.

### Core Value Proposition

- Answers grounded in YOUR materials, not generic knowledge
- Auto-generated quizzes that cite their source
- Mistake tracking that identifies weak concepts and adapts

---

## 2. Architecture

### System Architecture

```
┌─────────────────────────────────────────────────┐
│                  Next.js Frontend                │
│  Chat UI | Materials Mgmt | Quiz Cards | Review │
└────────────────────┬────────────────────────────┘
                     │ REST API + SSE
┌────────────────────▼────────────────────────────┐
│              FastAPI Backend                     │
│  ┌──────────────────────────────────────────┐   │
│  │     LangGraph StateGraph Orchestrator    │   │
│  │   (intent recognition → route → merge)   │   │
│  └──┬──────────┬──────────────┬─────────────┘   │
│     │          │              │                   │
│  ┌──▼──┐  ┌───▼───┐  ┌──────▼──────┐           │
│  │ RAG  │  │ Quiz  │  │  Tracker    │           │
│  │Agent │  │ Agent │  │  Agent      │           │
│  └──┬──┘  └───┬───┘  └──────┬──────┘           │
│     │         │              │                   │
│  ┌──▼─────────▼──────────────▼──────────────┐   │
│  │         Shared Services                  │   │
│  │  ChromaDB | LLM Adapter | File Parser   │   │
│  │  Hybrid Retrieval | Scheduler            │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### Three-Layer Agent Pattern

- **Layer 1 — Coordinator**: LangGraph StateGraph with intent recognition, routes to functional agents
- **Layer 2 — Functional Agents**: RAG Agent (Q&A), Quiz Agent (generation), Tracker Agent (scoring + mistake tracking)
- **Layer 3 — Specialists**: QuizGenerator, PaperAnalyzer, MistakeSummarizer — standalone LLM-powered modules called by Layer 2

### Agent Communication

Agents call each other through **shared service interfaces**, not direct agent-to-agent calls. This keeps agents decoupled and independently testable.

```
Orchestrator → RAG Agent       (user asks a question)
Orchestrator → Quiz Agent      (user requests a quiz)
Orchestrator → Tracker Agent   (user checks mistakes)
Quiz Agent   → RetrievalService (retrieve content before generating questions)
Quiz Agent   → TrackerService   (push mistakes after grading)
Tracker Agent → RetrievalService (retrieve content for weak areas)
Tracker Agent → QuizService     (trigger targeted quiz on weak concepts)
```

---

## 3. Agents

### RAG Agent

**Responsibility:** Answer questions based on uploaded materials with source citations.

**Workflow:**
1. Receive user question
2. Hybrid retrieval from ChromaDB (BM25 + dense + rerank)
3. Quality gate: refuse if no results meet relevance threshold
4. Assemble prompt with retrieved chunks + question
5. LLM generates answer with inline citations
6. Stream response via SSE

**Special capabilities:**
- User can specify "only use Material X" or "use all materials"
- Multi-query expansion for ambiguous questions
- Hypothetical Document Embeddings (HyDE) for hard queries

### Quiz Agent

**Responsibility:** Generate quiz questions grounded in source material.

**Workflow:**
1. Receive quiz request (topic, difficulty, count, material scope)
2. Call RAG Agent to retrieve relevant content
3. QuizGenerator specialist generates questions with source citations
4. Return interactive quiz cards
5. After user answers, delegate scoring to Tracker Agent

**Question types (MVP):** Multiple choice, fill-in-blank
**Question types (v1.1+):** Short answer with rubric scoring

**Quality controls:**
- Every question must cite source chunk (no source = no question)
- Distractors must be plausible (same domain, close values, common misconceptions)
- Per-question difficulty adjustment for diversity within a quiz

**Special capabilities:**
- "Generate 5 questions about Chapter 3"
- "Create a mock exam based on all materials"
- Adaptive difficulty from Tracker feedback

### Tracker Agent

**Responsibility:** Score answers, track mistakes, identify weak concepts, recommend review.

**Workflow (scoring):**
1. Receive answer from Quiz Agent
2. Score against rubric (multiple choice: exact match; short answer: key-point comparison)
3. If wrong: record mistake with concept tag, generate explanation with source citation
4. Push mistake to working memory and mistake summary

**Workflow (review):**
1. Identify weak concepts (accuracy rate < 60%)
2. Generate weak points report (donut chart + ranked list)
3. Can trigger Quiz Agent for targeted practice
4. Generate study plan based on exam date + weak concepts

**Knowledge model:** Two-level (topic > concept) with prerequisite edges, stored as JSON.

---

## 4. Shared Services

### Multi-Model Adapter

Unified interface for DeepSeek, MiniMax, GLM (primary), with OpenAI/Claude as optional fallback.

```python
class LLMService:
    async def invoke(self, prompt: str, model: str = None, **kwargs) -> str:
        provider = self._get_provider(model or self.default_model)
        try:
            return await provider.invoke(prompt, **kwargs)
        except (RateLimitError, ServiceUnavailableError):
            return await self._fallback(prompt, **kwargs)
```

- Exponential backoff with jitter (max 3 retries)
- Circuit breaker per provider
- Fallback chain: DeepSeek → GLM → MiniMax
- Log provider, model, latency_ms, token_count for observability

### Hybrid Retrieval Service

Three-stage pipeline: dual retrieval (BM25 + dense) → cross-encoder rerank → quality gate.

- Embedding model: bge-large-zh (Chinese-optimized)
- Reranker: bge-reranker-base
- Semantic chunking by section headers with overlap windows
- Chunk metadata: source file, chapter, page, heading

### File Parser Service

Async processing via ARQ (Redis-backed):

- PDF: PyMuPDF + OCR fallback
- Word: python-docx
- PPT: python-pptx
- Images: PaddleOCR / Tesseract
- Output: extracted text + page structure metadata
- Material.processing_status: pending → processing → ready / failed

### Spaced Repetition Scheduler

SM-2 algorithm variant, triggered after wrong answers:
- Schedule review at increasing intervals (1d → 3d → 7d → 14d → 30d)
- Adjust interval based on accuracy on review attempts

---

## 5. Data Models

```
User
  ├── 1:N → Conversation (chat session, tracks mode context)
  ├── 1:N → Material (uploaded files)
  │          ├── processing_status: pending|processing|ready|failed
  │          ├── error_detail: JSON
  │          └── 1:N → Chunk (stored in ChromaDB)
  │                     ├── chunk_index, embedding_model
  │                     └── metadata: {source, chapter, page, heading}
  ├── 1:N → QuizSession
  │          └── 1:N → Question
  │                     ├── question_type, difficulty, topic, concept
  │                     ├── source_chunk_ids (REQUIRED)
  │                     └── 1:1 → AnswerRecord
  │                                ├── student_answer, is_correct, score
  │                                └── time_taken_ms
  └── 1:N → MistakeRecord
             ├── attempt_count, last_reviewed_at, next_review_at
             └── N:1 → Concept (topic > concept two-level)

Concept ── N:N → Concept (via ConceptDependency with strength: float)
```

**Key indices:**
- `(user_id, next_review_at)` on MistakeRecord — scheduler queries
- `(user_id, material_id)` on Chunk — material-scoped retrieval

---

## 6. API Design

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST (SSE) | Streaming chat, orchestrator routes by intent |
| `/api/materials` | POST | Upload material (async parsing) |
| `/api/materials` | GET | List uploaded materials |
| `/api/materials/{id}` | DELETE | Delete material + cascade chunk cleanup |
| `/api/materials/{id}/reprocess` | POST | Reparse failed material |
| `/api/quiz/sessions` | GET | List quiz history |
| `/api/quiz/submit` | POST | Submit answer, trigger scoring |
| `/api/review/weak-points` | GET | Get weak concepts dashboard |
| `/api/review/mistakes` | GET | Get mistake history |
| `/api/review/study-plan` | POST | Generate study plan |
| `/api/health` | GET | Health check |

---

## 7. Frontend

### Tech Stack

- Next.js App Router + TailwindCSS
- State: Zustand (chat/quiz slices) + local state (materials)
- SSE: @microsoft/fetch-event-source (reconnect + Last-Event-ID)
- Virtualization: @tanstack/react-virtual (long chat histories)
- Charts: recharts
- Markdown + math: react-markdown + rehype-katex
- Upload: react-dropzone
- Accessibility: @radix-ui/react-radio-group

### Layout

Single-page chat application with:

- **Header**: Agent name | [Ask] [Quiz] [Review] mode switch | materials count badge
- **Materials Bar** (collapsible): drag-drop zone + file chips (icon + name + processing status)
- **Chat Stream**: unified message list with structured output
  - Text answers with inline citations
  - Definition cards, comparison tables, step-by-step lists
  - Interactive quiz cards (radiogroup + check button + collapsible explanation)
  - Weak points dashboard card (donut chart + ranked list + re-quiz action)
  - Floating quiz progress bar
- **Input Area**: mode-aware border color, supports /review command

### Component Architecture

```
<ChatLayout>
  <Header> → <ModeSwitch>, <MaterialsToggle>
  <MaterialsBar> → <FileChip>, <DropZone>
  <MessageList> → <StreamMessage>, <QuizCard>, <DashboardCard>,
                   <DefinitionCard>, <ComparisonTable>
  <ChatInput>
</ChatLayout>
```

### Key Interactions

| Scenario | Interaction |
|----------|-------------|
| Daily Q&A | Chat inline, structured output (cards/tables/lists) |
| Upload materials | Drag-drop in top bar, chips show processing status |
| Take quiz | Inline interactive cards, per-question or batch submit |
| Review mistakes | /review command or Review mode, inline dashboard card |
| Spaced repetition | Post-wrong-answer prompt: "Review in 2 days?" |
| Mode switch | Segmented control in header, input border color changes |

### Accessibility

- Quiz cards: radiogroup + radio pattern, arrow key navigation
- aria-live="polite" for feedback, aria-live="assertive" for score changes
- Keyboard navigation between quiz cards via Tab

### Frontend Design Workflow (Impeccable + Taste Skill)

The frontend will be designed and built using a two-skill workflow that ensures production-grade, anti-slop UI. This workflow is executed during the implementation phase.

#### Register: Product

This project is a **product register** (design SERVES the product). The UI is a tool for studying, not a marketing surface. The bar is **earned familiarity**: users fluent in Notion AI, ChatGPT, or Perplexity should trust this interface immediately.

Product register implications:
- One font family (system sans: Inter / system-ui stack), no display/body pairing
- Fixed rem scale (not fluid clamp), tighter ratio (1.125-1.2)
- Restrained color strategy: accent for primary actions + state indicators only
- State-rich semantic vocabulary: hover, focus, active, disabled, selected, loading, error, warning, success, info
- Motion conveys state only (150-250ms transitions), no decorative animation
- Consistent component vocabulary across all surfaces
- Standard navigation patterns (top bar + mode tabs)
- Density is a virtue; consistency over surprise

#### Phase 1: Shape (Design Brief via Impeccable)

Run `/impeccable shape` for each major surface before writing code. This produces a design brief through discovery, not guesswork.

**Discovery interview questions for this project:**

| Surface | Key Questions |
|---------|---------------|
| Chat layout | What's the primary user action? (ask questions) What's the user's mental state? (focused, exam-anxious) |
| Quiz cards | What states exist? (unanswered, selected, submitted-correct, submitted-wrong, explanation-expanded) What feedback timing? |
| Materials bar | What are realistic ranges? (0-20 files, 1-500 pages each) Empty state? (no materials uploaded) |
| Review dashboard | What data ranges? (0-50 weak concepts, 0-100% accuracy) How to handle cold start? |

**Design brief structure per surface:**
1. Feature Summary
2. Primary User Action
3. Design Direction (Restrained color + scene sentence + 2-3 anchor references: Perplexity, Notion AI, ChatGPT)
4. Scope (production-ready fidelity, interactive, polish until ships)
5. Layout Strategy
6. Key States (default, empty, loading, error, success, edge cases)
7. Interaction Model
8. Content Requirements
9. Recommended Impeccable references (layout.md, typeset.md, interaction-design.md, animate.md)
10. Open Questions

**Anchor references for visual direction:**
- Perplexity AI (cited answer cards, source chips)
- Notion AI (inline AI blocks, clean product UI)
- ChatGPT (streaming chat, mode switching)

#### Phase 2: Craft (Build via Impeccable)

Run `/impeccable craft` for each surface, following the craft flow:

1. **Shape confirmed** → lock design direction
2. **Load references** → layout.md, typeset.md, interaction-design.md, animate.md (minimum)
3. **Build to production quality** with these requirements:
   - Real content (no placeholder copy/images)
   - Semantic HTML (headings, landmarks, labels, form associations)
   - Deliberate spacing and alignment (no default gaps)
   - Intentional typography (chosen loading strategy, clear hierarchy, readable measure)
   - Full state coverage (default, hover, focus-visible, active, disabled, loading, error, success, empty)
   - Keyboard paths + touch targets + feedback timing
   - Coherent icon set (one library: Lucide)
   - Premium motion (state transitions, reduced-motion respected)
   - Production build passes, no console errors
4. **Iterate visually** → inspect in browser, critique against brief, patch defects
5. **Present** → show primary state, key states, design decisions

#### Phase 3: Taste Skill (Anti-Slop Quality Gate)

After each surface is crafted, run the **design-taste-frontend** skill as a quality gate:

- Audit for AI slop patterns (gradient text, side-stripe borders, identical card grids, uppercase eyebrows, glassmorphism defaults)
- Verify the interface does NOT look like a default AI template
- Check that the design reads as intentional and product-specific
- Ensure visual hierarchy through scale contrast (not just color)
- Verify spacing rhythm (not uniform padding everywhere)

#### Phase 4: Critique + Polish (Impeccable)

After Taste Skill passes, run the Impeccable quality loop:

1. `/impeccable critique` → dual assessment (design review + detector/browser evidence)
   - AI slop check, heuristic scoring (Nielsen 10), cognitive load, emotional journey
   - Detector scan for anti-patterns (low contrast, gradient text, side tabs, etc.)
2. `/impeccable polish` → final quality pass addressing critique findings
3. `/impeccable audit` → technical quality checks (a11y, perf, responsive)

#### Phase 5: Onboard (Impeccable)

Run `/impeccable onboard` for the first-run experience:

- Design the empty state when no materials are uploaded (teach the interface)
- Design the first-quiz flow (get users to "aha moment" fast)
- Make onboarding optional (skip button, don't block access)
- Show, don't tell: demonstrate with working examples

#### Execution Order

The workflow is executed surface-by-surface in this order:

| Step | Surface | Skills Used | Output |
|------|---------|-------------|--------|
| 1 | ChatLayout + Header + Input | shape → craft → taste → critique → polish | Core chat shell |
| 2 | MaterialsBar + FileChip + DropZone | shape → craft → taste → critique → polish | Upload experience |
| 3 | QuizCard + progress bar | shape → craft → taste → critique → polish | Interactive quiz |
| 4 | DashboardCard (review) | shape → craft → taste → critique → polish | Weak points view |
| 5 | DefinitionCard + ComparisonTable | shape → craft → taste → polish | Structured output |
| 6 | Onboard (empty states) | onboard → taste → polish | First-run experience |
| 7 | Full audit | audit | Cross-surface consistency, a11y, perf |

#### Impeccable Design Rules for This Project

From the product register, these rules are binding:

- **Color**: Restrained strategy. Accent color for primary actions + mode indicators only. State-rich semantic vocabulary. No saturated backgrounds.
- **Typography**: One family (Inter / system-ui). Fixed rem scale. Tighter ratio (1.125-1.2). Body line length 65-75ch for prose.
- **Layout**: Responsive behavior is structural (collapse materials bar, responsive quiz cards), not fluid typography.
- **Components**: Every interactive component has all states (default, hover, focus, active, disabled, loading, error). Skeleton states for loading. Empty states that teach.
- **Motion**: 150-250ms transitions. Motion conveys state only. No page-load sequences. Reduced-motion respected.
- **Copy**: Verb + object button labels. No em dashes. No marketing buzzwords. Every word earns its place.
- **Bans**: No side-stripe borders, no gradient text, no glassmorphism as default, no identical card grids, no uppercase eyebrows, no display fonts in UI labels, no decorative motion, no modal as first thought

---

## 8. Backend Directory Structure

```
backend/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   └── middleware.py
│   ├── orchestrator/
│   │   ├── graph.py          # LangGraph StateGraph
│   │   ├── state.py          # Shared state model
│   │   └── router.py         # Intent recognition + routing
│   ├── agents/
│   │   ├── rag_agent.py
│   │   ├── quiz_agent.py
│   │   └── tracker_agent.py
│   ├── specialists/
│   │   ├── quiz_generator.py
│   │   ├── paper_analyzer.py
│   │   └── mistake_summarizer.py
│   ├── services/
│   │   ├── llm_service.py    # Multi-model adapter
│   │   ├── embedding_service.py
│   │   ├── retrieval_service.py  # Hybrid BM25+dense+rerank
│   │   ├── parser_service.py     # PDF/Word/PPT/OCR
│   │   └── scheduler_service.py  # Spaced repetition
│   ├── db/
│   │   ├── vector_store.py   # ChromaDB wrapper
│   │   └── models.py         # SQLAlchemy models (SQLite for dev, PostgreSQL for prod)
│   ├── schemas/              # Pydantic request/response
│   │   ├── chat.py
│   │   ├── materials.py
│   │   ├── quiz.py
│   │   └── review.py
│   ├── tasks/                # ARQ async tasks
│   │   └── parse_material.py
│   └── api/
│       ├── chat.py           # SSE streaming
│       ├── materials.py
│       ├── quiz.py
│       └── review.py
```

---

## 9. Feature Prioritization

### MVP (Weeks 1-4)

- RAG Q&A with source citations
- Quiz generation (multiple choice + fill-in-blank)
- Mistake tracking with two-level concept model
- Multi-model support (DeepSeek, MiniMax, GLM)
- Basic chat UI with mode switching
- File upload and parsing

### v1.1 (Weeks 5-6)

- Adaptive difficulty (Tracker → Quiz feedback loop)
- Wrong answer explanation with source citations
- Study plan generation
- Weak points dashboard
- Quiz progress tracking

### v1.2 (Nice-to-Have)

- Spaced repetition scheduling
- Concept coverage report
- Evaluation harness (gold Q&A pairs)
- Short answer questions with rubric scoring
- Offline support (IndexedDB queue)

---

## 10. Security

- File upload: validate MIME type + magic bytes, cap 50MB, UUID filenames
- Prompt injection: delimit user input in system prompts, lightweight classifier to reject manipulation
- Auth: JWT-based (signup/login endpoints), row-level security on Material/Chunk/MistakeRecord filtered by user_id
- Rate limiting: per-user on /api/chat (LLM cost) and /api/materials POST (upload abuse)
- Never return raw LLM output in error responses
- ChromaDB: collection-per-user isolation to prevent cross-user data leakage

---

## 11. Interview Demo Flow

1. **Upload a PDF** → ask a question → show cited answer (proves RAG, 2 min)
2. **Switch to Quiz mode** → generate quiz → answer wrong → show explanation with source (proves generation + citation, 2 min)
3. **Switch to Review** → show weak concepts → generate study plan (proves stateful tracking + planning, 2 min)
4. **Swap model** (DeepSeek → GLM) → same quiz, different style (proves model abstraction, 1 min)

---

## 12. Product Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Cold start (no mistake data initially) | Auto-generate diagnostic quiz on material upload |
| Quiz hallucination | Every question must cite source chunk; no source = no question |
| Mode confusion | Explicit pill/toggle for mode switching, not implicit keyword detection |
| Citation fragility | Overlap windows in chunking; validate citation exists before displaying |
| Scoring inconsistency (LLM nondeterminism) | Use rubric-based scoring for short answer; exact match for MC |
| ChromaDB scaling under multi-user | Collection-per-tenant pattern; migrate to Qdrant if needed |

---

## 13. Reusable Skills Created

| Skill | Location | Applied To |
|-------|----------|------------|
| agent-three-layer-architecture | skills/agent-three-layer-architecture/ | Agent architecture design |
| rag-hybrid-retrieval | skills/rag-hybrid-retrieval/ | Retrieval service implementation |
| adaptive-quiz-generation | skills/adaptive-quiz-generation/ | Quiz Agent + QuizGenerator |
| agent-hybrid-summary | skills/agent-hybrid-summary/ | Mistake summary management |
| agent-working-memory | skills/agent-working-memory/ | Tracker Agent memory |

---
name: agent-three-layer-architecture
description: Design and implement multi-agent systems using the three-layer architecture pattern (Coordinator → Functional Agents → Specialists). Use this skill when building any multi-agent system, agent orchestration, or when you need to separate routing logic from domain behavior from LLM-powered capabilities. Also use when the user mentions "agent architecture", "multi-agent", "agent orchestration", "coordinator pattern", or "agent layers".
---

# Three-Layer Agent Architecture

A proven pattern for building multi-agent systems with clear separation of concerns. Derived from the [hello-agents](https://github.com/datawhorechina/hello-agents) LearningAgent project.

## Why Three Layers?

Most multi-agent systems fail because they mix routing, domain logic, and LLM calls in one place. The three-layer pattern forces each concern into its own layer, making the system testable, debuggable, and extensible.

## The Layers

### Layer 1 — Coordinator (Routing + Intent Recognition)

The top-level agent that receives user input, identifies intent, and routes to the correct functional agent.

**Key patterns:**

```python
class MainAgent(SimpleAgent):
    INTENT_KEYWORDS = {
        "quiz": ["出题", "测试", "quiz", "考试", "模拟题"],
        "qa": ["解释", "什么是", "为什么", "how", "what"],
        "review": ["错题", "薄弱", "复习", "review", "弱项"],
    }

    def process_command(self, user_input: str):
        # 1. Check for active sessions first (continuation > new intent)
        if self.active_session:
            return self.active_session.continue_(user_input)

        # 2. Identify intent via keyword matching
        intent = self._classify_intent(user_input)

        # 3. Route to functional agent
        return self._route(intent, user_input)

    def _classify_intent(self, text: str) -> str:
        scores = {}
        for intent, keywords in self.INTENT_KEYWORDS.items():
            scores[intent] = sum(1 for kw in keywords if kw in text.lower())
        return max(scores, key=scores.get) if any(scores.values()) else "qa"
```

**Design rules:**
- Active sessions take priority over new intent detection (a student mid-quiz should continue the quiz, not start a new Q&A)
- Intent classification can start with keywords and evolve to LLM-based classification as complexity grows
- The coordinator owns no domain knowledge — it only routes

### Layer 2 — Functional Agents (Domain Behavior)

Domain-specific agents that handle one area of functionality. Each manages its own session state and calls specialists for LLM-powered work.

```python
class QuizAgent(ReActAgent):
    """Handles quiz generation, answer collection, and scoring."""

    def __init__(self, llm, rag_service, tracker_service):
        super().__init__(llm)
        self.quiz_generator = QuizGenerator(llm)  # Layer 3 specialist
        self.rag = rag_service                     # Shared service
        self.tracker = tracker_service             # For pushing mistakes
        self.active_session = None

    def start_quiz(self, topic: str, difficulty: float, count: int):
        # 1. Retrieve relevant content via RAG
        chunks = self.rag.search(topic, top_k=10)

        # 2. Generate questions grounded in retrieved content
        questions = self.quiz_generator.generate(
            chunks=chunks,
            difficulty=difficulty,
            count=count
        )
        self.active_session = QuizSession(questions)
        return questions

    def submit_answer(self, question_id: str, answer: str):
        result = self.active_session.grade(question_id, answer)
        if not result.correct:
            self.tracker.record_mistake(result)  # Push to Tracker
        return result
```

**Design rules:**
- Each functional agent owns one domain (quiz, Q&A, review)
- Agents call Layer 3 specialists for LLM work, not the LLM directly
- Agents can call other agents' services (Quiz → Tracker) through shared service interfaces, not direct agent-to-agent calls
- Session state lives on the functional agent (`self.active_session`)

### Layer 3 — Specialists (LLM-Powered Modules)

Standalone, single-responsibility modules that wrap LLM calls. They are NOT agents — they have no routing, no state, no session management. They take input and return output.

```python
class QuizGenerator:
    """Generates quiz questions grounded in source material."""

    def __init__(self, llm):
        self.llm = llm

    def generate(self, chunks: list[Chunk], difficulty: float, count: int) -> list[Question]:
        questions = []
        for i in range(count):
            # Per-question difficulty adjustment for diversity
            adjusted = min(1.0, difficulty + (i - count // 2) * 0.1)
            q = self._generate_one(chunks, adjusted)
            questions.append(q)
        return questions

    def _generate_one(self, chunks, difficulty) -> Question:
        prompt = self._build_prompt(chunks, difficulty)
        response = self.llm.invoke(prompt)
        return self._parse(response, source_chunks=chunks)
```

**Design rules:**
- Specialists are pure functions with LLM access — no state, no routing
- Every output must carry source references (for citation and hallucination prevention)
- Keep specialists small and focused — one specialist per LLM task

## Data Flow Between Layers

```
User Input
    │
    ▼
┌──────────────┐
│  Coordinator  │  Intent → Route
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Functional   │  Domain logic + Session state
│  Agent        │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Specialist   │  LLM call + Source grounding
└──────────────┘
```

**Cross-agent communication** happens through shared services, not direct agent calls:
- Quiz Agent → Tracker Service (push mistakes after grading)
- Tracker Agent → RAG Service (retrieve content for weak areas)
- Tracker Agent → Quiz Service (trigger targeted quiz)

## When to Use This Pattern

- **Use it** when you have 2+ distinct user intents that need different agent behaviors
- **Use it** when agents need to share state or communicate (e.g., quiz results feeding a tracker)
- **Use it** when you want each agent independently testable

- **Don't use it** for single-purpose agents (one layer is enough)
- **Don't use it** when LLM function calling alone solves the problem (simpler is better)

## Evolution Path

Start simple, add layers as complexity grows:

1. **Start:** Single agent with function calling (Layer 2 only)
2. **Add routing:** When you have 2+ intents, add a Coordinator (Layer 1)
3. **Extract specialists:** When LLM calls get complex, extract to Layer 3
4. **Add cross-agent communication:** When agents need to share results

## Source

This pattern is derived from the [LearningAgent](https://github.com/datawhorechina/hello-agents/tree/main/Co-creation-projects/Yixiang-Wu-LearningAgent) project in the Datawhale hello-agents curriculum.

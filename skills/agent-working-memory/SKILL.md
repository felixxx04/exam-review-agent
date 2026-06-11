---
name: agent-working-memory
description: Implement working memory for AI agents with capacity limits, TTL-based cleanup, and multi-signal retrieval (semantic + keyword + recency + importance). Use this skill when building agent memory systems, context management, or when the user mentions "agent memory", "working memory", "context window", "memory management", "agent state", or "conversation memory". Critical for agents that need to remember and prioritize information across interactions.
---

# Agent Working Memory

Agents need memory that doesn't grow unbounded. Working memory implements capacity limits, automatic cleanup, and smart retrieval that considers multiple signals.

Based on `code/chapter8/03_WorkingMemory_Implementation.py` from hello-agents.

## Core Design

```python
class WorkingMemory:
    def __init__(self, capacity: int = 50, default_ttl: int = 3600):
        self.capacity = capacity
        self.default_ttl = default_ttl
        self.items: list[MemoryItem] = []

    def add(self, content: str, importance: float = 0.5,
            ttl: int = None, tags: list[str] = None):
        item = MemoryItem(
            content=content,
            importance=importance,  # 0.0-1.0
            created_at=time.now(),
            expires_at=time.now() + (ttl or self.default_ttl),
            tags=tags or [],
            access_count=0,
        )
        self.items.append(item)
        self._evict_if_needed()

    def retrieve(self, query: str, top_k: int = 5) -> list[MemoryItem]:
        """Multi-signal retrieval combining four factors."""
        scored = []
        for item in self.items:
            score = (
                0.3 * self._semantic_similarity(query, item) +
                0.2 * self._keyword_match(query, item) +
                0.2 * self._recency_score(item) +
                0.3 * self._importance_score(item)
            )
            scored.append((item, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [item for item, _ in scored[:top_k]]
```

## The Four Retrieval Signals

| Signal | Weight | What it captures |
|--------|--------|-----------------|
| Semantic similarity | 0.3 | Is this memory about the same topic? |
| Keyword match | 0.2 | Does it contain the exact terms? |
| Recency | 0.2 | Was this memory created recently? |
| Importance | 0.3 | Was this flagged as important? |

Adjust weights based on your use case:
- **Mistake tracking**: Boost importance weight (wrong answers should be prioritized)
- **Conversation context**: Boost recency weight (recent messages matter more)
- **Knowledge retrieval**: Boost semantic weight (conceptual relevance matters most)

## TTL and Automatic Cleanup

```python
def cleanup_expired(self):
    """Remove items past their TTL."""
    now = time.now()
    self.items = [item for item in self.items if item.expires_at > now]
```

Run cleanup on every `add()` and periodically. TTL values:
- Conversation turns: 30 minutes
- Mistake records: 30 days (or until exam date)
- Important concepts: No expiry (importance=1.0, TTL=infinite)

## Priority-Based Eviction

When capacity is exceeded, evict the least valuable items:

```python
def _evict_if_needed(self):
    while len(self.items) > self.capacity:
        # Score each item for eviction (lowest = first to go)
        eviction_scores = []
        for item in self.items:
            score = (
                item.importance * 0.5 +
                self._recency_score(item) * 0.3 +
                (item.access_count / max_access) * 0.2
            )
            eviction_scores.append((item, score))

        # Remove the lowest-scoring item
        evicted = min(eviction_scores, key=lambda x: x[1])
        self.items.remove(evicted[0])
```

## Applying to Exam Review Agent

```python
class MistakeMemory(WorkingMemory):
    """Working memory specialized for tracking student mistakes."""

    def record_mistake(self, question: Question, student_answer: str):
        self.add(
            content=f"Q: {question.text} | Your answer: {student_answer} | Correct: {question.correct_answer}",
            importance=0.8,  # Mistakes are high importance
            ttl=30 * 24 * 3600,  # 30 days
            tags=[question.topic, question.concept],
        )

    def get_weak_concepts(self) -> list[tuple[str, float]]:
        """Identify concepts with most mistakes."""
        concept_counts = defaultdict(lambda: {"total": 0, "wrong": 0})
        for item in self.items:
            for tag in item.tags:
                concept_counts[tag]["total"] += 1
                if item.importance > 0.7:  # Was a mistake
                    concept_counts[tag]["wrong"] += 1
        return sorted(
            [(c, d["wrong"] / d["total"]) for c, d in concept_counts.items()],
            key=lambda x: x[1], reverse=True
        )
```

## Source

Derived from `code/chapter8/03_WorkingMemory_Implementation.py` in the hello-agents project.

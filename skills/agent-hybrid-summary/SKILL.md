---
name: agent-hybrid-summary
description: Implement hybrid summary management for agent knowledge bases that grow over time — using full rewrite for small knowledge bases and incremental merge for large ones. Use this skill when building agent memory systems, knowledge base management, incremental summarization, or when the user mentions "summary update", "knowledge management", "incremental summary", "agent memory", or "knowledge base growth".
---

# Hybrid Summary Management

As an agent accumulates knowledge (e.g., mistake records, study notes), the summary must stay compact and current. A full LLM rewrite on every update is wasteful; simple append loses coherence. The hybrid strategy picks the right approach based on knowledge base size.

Based on `core/summary_manager.py` from the hello-agents LearningAgent project.

## The Threshold-Based Strategy

```python
class SummaryManager:
    FULL_REWRITE_THRESHOLD = 5  # files/items

    def update_summary(self, knowledge_dir: str, new_content: str) -> str:
        file_count = count_files(knowledge_dir)

        if file_count < self.FULL_REWRITE_THRESHOLD:
            return self._full_rewrite(knowledge_dir, new_content)
        else:
            return self._incremental_merge(knowledge_dir, new_content)

    def _full_rewrite(self, knowledge_dir: str, new_content: str) -> str:
        """Read all files + new content, ask LLM to rewrite entire summary."""
        all_content = read_all_files(knowledge_dir) + "\n" + new_content
        summary = self.llm.invoke(f"请将以下内容整理为一份简洁的知识摘要:\n{all_content}")
        save_summary(summary)
        return summary

    def _incremental_merge(self, knowledge_dir: str, new_content: str) -> str:
        """Read existing summary + new content, ask LLM to merge."""
        existing = read_summary()
        merged = self.llm.invoke(
            f"现有摘要:\n{existing}\n\n新内容:\n{new_content}\n\n"
            f"请将新内容整合到现有摘要中，保持简洁，移除重复。"
        )
        save_summary(merged)
        return merged

    def _fallback(self, knowledge_dir: str, new_content: str) -> str:
        """When LLM fails, simple concatenation or append."""
        existing = read_summary()
        if existing:
            return existing + "\n\n---\n\n" + new_content
        return new_content
```

## Why This Matters

| Approach | When | Cost | Quality |
|----------|------|------|---------|
| Full rewrite | < 5 items | Low (small input) | High (coherent) |
| Incremental merge | >= 5 items | Medium (grows slowly) | Good (may drift) |
| Simple append | LLM failure | Zero | Low (no dedup) |

The key insight: small knowledge bases benefit from full rewrites (LLM sees everything and produces a coherent summary). Large knowledge bases are too expensive to rewrite fully, so incremental merge is the practical choice.

## Applying to Mistake Tracking

This pattern directly maps to maintaining a compact mistake knowledge base:

```python
class MistakeSummaryManager(SummaryManager):
    """Track student weaknesses as a growing, compact summary."""

    def update_after_mistake(self, mistake: MistakeRecord):
        new_entry = f"知识点: {mistake.concept}, 错误: {mistake.student_answer}, 正确: {mistake.correct_answer}"

        summary = self.update_summary(self.mistake_dir, new_entry)

        # Periodic full rewrite to prevent drift
        if self.update_count % 10 == 0:
            summary = self._full_rewrite(self.mistake_dir, "")
            self.update_count = 0
```

## Periodic Full Rewrite for Drift Prevention

Incremental merging gradually drifts — early details get compressed, recent details dominate. Schedule periodic full rewrites:

- Every N updates (e.g., every 10 mistakes)
- When summary length exceeds a threshold
- When the user explicitly requests a review

## Source

Derived from `core/summary_manager.py` in the hello-agents LearningAgent project.

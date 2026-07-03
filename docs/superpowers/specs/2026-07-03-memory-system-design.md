# Memory System Design

## Goal

Build a first-version memory system for the local single-user exam review Agent. The system should let the Agent remember prior questions across browser refreshes and project restarts, preserve useful study context, and use that context in Ask, Quiz, and Review flows.

This version keeps the existing `user_id="default"` approach. It does not add registration, login, multi-user account management, or permission handling.

## Current State

The frontend currently keeps messages in the Zustand chat store so the current page can render a visible chat history. The backend chat endpoint only receives the current `message` and `material_scope`, then calls `run_orchestrator` with a single `HumanMessage`.

The database already has a useful foundation: `User`, `Conversation`, `Material`, `QuizSession`, `Question`, `AnswerRecord`, `MistakeRecord`, and `Concept`. However, the project does not yet persist individual chat messages, inject previous conversation history into the Agent, or maintain a durable learning profile.

## Target Behavior

The first version should support these user-visible outcomes:

- A user can refresh the page or restart the project and still see previous chat messages.
- The Agent can answer follow-up questions such as "刚才那个概念再举个例子" by using recent conversation history.
- The Agent can remember the user's current subject, review goal, weak concepts, frequent questions, and active materials across sessions.
- Long conversations stay usable by combining a concise summary with the most recent messages instead of injecting the full history every time.
- Quiz and Review can later use the same memory layer to generate more relevant questions and review suggestions.

## Data Model Changes

### Conversation

Extend the existing `Conversation` model with memory-oriented fields:

- `summary`: compressed summary of older conversation history.
- `message_count`: total saved messages in the conversation.
- `last_message_at`: timestamp for the latest user or assistant message.
- `last_memory_updated_at`: timestamp for the latest summary or learning-profile update.

`Conversation` remains the durable container for one chat thread.

### ConversationMessage

Add a new table for each persisted chat message.

Fields:

- `id`
- `conversation_id`
- `role`: `user`, `assistant`, or `system`
- `content`
- `material_scope`: JSON list of material filenames or identifiers used for that turn
- `metadata`: JSON object for citations, mode, intent, model info, and other future details
- `created_at`

This table is the source of truth for restoring chat history and building recent-message context.

### LearningProfile

Add a new table for cross-session study memory for the default user.

Fields:

- `id`
- `user_id`
- `current_subject`
- `review_goal`
- `weak_concepts`: JSON array
- `frequent_questions`: JSON array
- `active_materials`: JSON array
- `preferences`: JSON object for stable answer or study preferences
- `updated_at`

JSON fields keep the first version flexible. If reporting or analytics become more important later, these can be normalized into separate tables.

### MaterialChunk

Add a new table for material chunk metadata.

Fields:

- `id`
- `material_id`
- `chunk_id`: identifier that matches the vector store chunk id
- `text_preview`
- `page_number`
- `token_count`
- `embedding_id`
- `created_at`

This lets the app trace citations, debug parsing, and delete relational chunk metadata when a material is deleted.

### Material

Extend `Material` with:

- `storage_path`
- `mime_type`
- `hash`
- `processed_at`
- `parse_error`

`hash` helps detect duplicate uploads. `storage_path` makes storage behavior explicit instead of relying only on generated filenames.

### AnswerRecord

Extend `AnswerRecord` with:

- `quiz_session_id`
- `feedback`
- `score`

This makes answer history easier to connect to quiz sessions and review analytics.

## Memory Service

Add a backend `MemoryService` that owns memory operations instead of putting that logic directly into API handlers.

Responsibilities:

- Get or create the default active conversation.
- Save user messages.
- Save assistant messages after streaming completes.
- Fetch recent messages for context injection.
- Fetch and update `Conversation.summary`.
- Fetch and update `LearningProfile`.
- Build a `memory_context` object for the orchestrator.
- Decide when to update summary and learning profile.

The chat API should orchestrate request flow, while `MemoryService` handles persistence and memory policy.

## Chat Flow

The new `/api/chat` flow should be:

1. Validate the user message with the prompt-injection guard.
2. Get or create the active conversation for `user_id="default"`.
3. Save the user message as `ConversationMessage`.
4. Load memory context:
   - `LearningProfile`
   - `Conversation.summary`
   - recent conversation messages
   - selected material scope
5. Call the orchestrator with the current message and memory context.
6. Stream the assistant response to the frontend.
7. Save the completed assistant message.
8. Update message counters and timestamps.
9. If thresholds are met, update the summary and learning profile.

If streaming fails after the user message is saved, the system should either save an assistant error message in metadata or leave the user message without a paired assistant response. The first version can keep this simple and log the failure.

## Context Injection

The Agent should not receive every historical message. Each turn should inject a bounded context:

1. Current user question.
2. Selected material retrieval results.
3. Recent messages, such as the latest 6 turns.
4. Conversation summary.
5. Learning profile.

Priority order:

1. Current user question
2. Retrieved material chunks
3. Recent messages
4. Conversation summary
5. Learning profile

The current question and retrieved materials should override older memory when they conflict.

Example context shape:

```text
用户学习状态:
- 当前科目: 数据库系统
- 当前目标: 理解事务隔离级别
- 薄弱知识点: 幻读、可重复读

本会话摘要:
用户之前询问了事务 ACID、隔离级别、幻读和不可重复读的区别。

最近对话:
user: ...
assistant: ...
user: ...

当前问题:
...
```

`run_orchestrator` should be updated so it can receive either a prepared message list or a structured `memory_context`. The implementation should follow the existing LangGraph state pattern and keep routing behavior testable.

## Summary Updates

The summary should update only when useful. First-version triggers:

- Every 6 saved messages.
- Or when unsummarized recent text exceeds roughly 3000 to 5000 Chinese characters.
- Or when the topic changes clearly.

The summary prompt should combine the previous summary and recent unsummarized messages, then produce a concise new summary.

Summary rules:

- Preserve study goal, discussed concepts, unresolved confusion, and important user preferences.
- Remove greetings, repeated wording, and low-value small talk.
- Avoid storing secrets or sensitive personal information.
- Keep the summary around 300 to 800 Chinese characters.

The full message history remains stored in `ConversationMessage`; summary is only a context compression tool.

## Learning Profile Updates

Learning profile updates should be conservative. After a completed assistant response, a constrained extraction step can ask the LLM for JSON with only approved fields:

```json
{
  "current_subject": "数据库系统",
  "review_goal": "理解事务隔离级别",
  "weak_concepts": ["幻读", "可重复读"],
  "frequent_questions": ["事务隔离级别区别"],
  "active_materials": ["数据库课件.pdf"],
  "preferences": {
    "answer_style": "希望用例子解释"
  }
}
```

Backend merge policy:

- `current_subject` changes only when the user explicitly mentions a subject.
- `review_goal` changes when the user states a clear goal or asks repeatedly about the same goal.
- `weak_concepts` are deduplicated and appended.
- `frequent_questions` keep a bounded recent list.
- `active_materials` are updated from selected material scope.
- `preferences` store stable preferences only, not one-off phrasing.

The backend must ignore unknown fields from the LLM output.

## API Changes

Minimum first-version API surface:

- `POST /api/chat`: sends a message, persists memory, streams the assistant response.
- `GET /api/conversations/active`: returns the default active conversation.
- `GET /api/conversations/{id}/messages`: returns persisted messages for page restore.
- `GET /api/memory/profile`: returns the current learning profile.

Optional later APIs:

- `POST /api/conversations`
- `DELETE /api/conversations/{id}`
- `PATCH /api/memory/profile`

The first version does not need a full conversation management UI.

## Frontend Changes

The frontend should stay small in the first version:

- Add `conversationId` to the chat store.
- On page load, request the active conversation and its messages.
- Render restored messages in the existing `MessageList`.
- Send `conversation_id` with chat requests once known.
- Accept a returned or streamed conversation id if the backend creates one.

Later UI improvements can include conversation lists, manual reset, generated conversation titles, and a memory profile panel.

## Integration With Existing Features

Ask:

- Uses recent conversation history, summary, learning profile, and selected material scope.

Quiz:

- Can later use `weak_concepts`, `active_materials`, and previous mistakes to generate better questions.

Review:

- Can combine `MistakeRecord`, `AnswerRecord`, and `LearningProfile` to produce better weak-point dashboards.

Materials:

- Stores chunk metadata in `MaterialChunk`.
- Deleting a material should delete its chunk rows and vector-store chunks.

## Implementation Phases

### Phase 1: Durable Memory Foundation

- Add migrations and models.
- Implement `MemoryService` create/read/save operations.
- Persist user and assistant chat messages.
- Restore messages on frontend page load.
- Keep `user_id="default"`.

### Phase 2: Context Injection And Summary

- Update orchestrator input to include memory context.
- Inject summary, recent messages, and learning profile.
- Add summary update thresholds.
- Add tests for context construction and summary update decisions.

### Phase 3: Learning State And Review Linkage

- Add constrained learning-profile extraction.
- Merge extracted JSON into `LearningProfile`.
- Use `weak_concepts` and `active_materials` in Quiz and Review.
- Add tests for profile merge behavior.

## Testing Strategy

Backend tests:

- Active default conversation can be created and reused.
- User and assistant messages are saved in order.
- Conversation history can be restored after a new request.
- Memory context includes summary, recent messages, and learning profile.
- Summary update triggers only at expected thresholds.
- Learning profile merge deduplicates concepts and ignores unknown fields.
- Material deletion removes `MaterialChunk` rows and associated vector chunks.

Frontend tests:

- Page load restores persisted messages.
- Sending a message includes `conversation_id` when available.
- Empty history still renders the existing empty state.
- Streaming completion does not duplicate assistant messages.

Acceptance checks:

- The Agent can answer a follow-up question that depends on the previous turn.
- Restarting frontend and backend does not erase chat history.
- The Agent can recall the current subject and weak concepts from the learning profile.
- Long conversations stay bounded by summary plus recent messages.

## Risks And Controls

Memory pollution:

- Use whitelist extraction fields and conservative merge rules.
- Do not overwrite key fields unless user intent is explicit.

Context bloat:

- Inject summary and recent messages, not the full history.
- Keep recent history window configurable.

Overly complex schema:

- Use JSON fields for flexible first-version profile data.
- Normalize later only when reporting needs become clearer.

Sensitive information:

- Do not intentionally store API keys, secrets, or unrelated personal details in summary or profile.
- Ignore likely secret-like values during profile extraction.

## Non-Goals

- No login or JWT user flow in this version.
- No multi-user permissions.
- No advanced recommendation engine.
- No full conversation management UI.
- No separate long-term vector memory store for user preferences in the first version.

## Success Criteria

The design is complete when the app can:

- Persist chat messages to the database.
- Restore previous messages after refresh or restart.
- Inject summary, recent messages, and learning profile into Agent calls.
- Maintain a default user's learning profile across sessions.
- Keep the design compatible with later multi-user support by replacing `default` with a real user id.

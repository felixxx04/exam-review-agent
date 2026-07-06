# Review Workbench Design

## 1. Background

The current Review page only shows weak concept statistics and a `再测` action. It does not yet behave like a real mistake-review workspace: users cannot browse wrong answers, inspect details, write corrections, mark mastery, build a daily review set, or follow a multi-day plan.

This design turns Review mode into a three-phase `错题工作台`:

1. Phase 1: Build the core mistake-book loop.
2. Phase 2: Add guided daily review and smarter remediation.
3. Phase 3: Add long-term review intelligence and export/source enhancements.

Implementation must wait for user approval of this design document. After approval, each phase is implemented, verified, and self-reviewed before moving to the next phase.

## 2. Goals

- Make the Review page useful immediately after a user answers quiz questions incorrectly.
- Let users find, inspect, correct, retest, and mark mistake records.
- Preserve the existing Ask / Quiz / Review mental model.
- Reuse the current backend concepts where possible: `mistake_records`, weak concepts, quiz generation, and study plan generation.
- Keep the first implementation practical while leaving clear room for more advanced review behavior.

## 3. Non-Goals

- No full PDF reader or source-document annotation UI in the first phase.
- No complex spaced-repetition algorithm in the first phase.
- No unrelated redesign of Ask or Quiz mode.
- No wholesale backend persistence rewrite unless existing storage blocks the needed behavior.

## 4. Product Shape

Review mode becomes a three-column workspace on desktop and a list-first flow on mobile.

### Desktop Layout

Top summary band:

- `待复习错题数`
- `薄弱知识点数`
- `平均正确率`
- `今日建议复习量`
- Primary actions: `开始今日复习`, `生成复习计划`, `刷新错题`

Left column: filters and weak concepts.

- Status filters: `全部`, `未订正`, `已订正`, `需再测`, `已掌握`, `高频错误`
- Concept filter
- Topic/material filter where data is available
- Question type filter
- Sort options: priority, latest wrong answer, mistake count
- Weak concept ranking with quick `再测` actions

Middle column: mistake list.

- Question summary
- Concept and topic
- Question type
- Attempt/mistake count
- Last wrong time
- Status tag
- Quick actions: `加入今日复习`, `再测该知识点`

Right column: mistake detail and operations.

- Original question text
- User's wrong answer
- Correct answer
- Explanation or generated wrong-answer explanation
- Source material/chunk metadata when available
- Correction note editor
- Actions: `保存订正`, `标记已掌握`, `取消掌握`, `生成相似题`, `查看来源`

### Mobile Layout

Mobile uses a list-first layout:

- Summary band becomes horizontally scrollable compact metrics.
- Filters collapse into a top filter drawer.
- Mistake list is primary.
- Tapping a mistake opens a full-height detail drawer or detail screen.

## 5. Complete Feature Set

### 5.1 Summary and Prioritization

- Show total mistake count.
- Show pending review count.
- Show mastered count.
- Show weak concept count.
- Show average accuracy using the existing weak-point data.
- Compute a default priority order:
  - `未订正` first.
  - `需再测` second.
  - higher attempt count before lower attempt count.
  - recent wrong answers before old wrong answers.

### 5.2 Mistake Search and Filtering

- Search by question text and concept.
- Filter by status:
  - `unreviewed`: wrong answer recorded but no correction note.
  - `corrected`: correction note saved.
  - `needs_requiz`: corrected but not yet retested.
  - `mastered`: user marked as mastered.
- Filter by concept.
- Filter by topic.
- Filter by material/source if material metadata exists.
- Filter by question type.
- Sort by priority, latest wrong time, and mistake count.

### 5.3 Mistake List

Each mistake item should show:

- question summary
- concept
- topic
- question type
- wrong answer preview when useful
- attempt count
- last wrong time
- status tag

List interactions:

- Click item to open details.
- `加入今日复习` adds the item to the daily session queue.
- `再测该知识点` generates a quiz for that mistake's concept.

### 5.4 Mistake Detail

The detail panel should show:

- original question
- user's wrong answer
- correct answer
- explanation
- concept and topic
- source material/chunk metadata if available
- correction note
- status history where available

Detail actions:

- `保存订正`: saves the user's correction note and marks the item as `corrected`.
- `标记已掌握`: marks item as `mastered` and removes it from the default pending list.
- `取消掌握`: restores item to the reviewable list.
- `生成相似题`: generates similar practice based on the concept and question context.
- `查看来源`: displays source metadata first; later can jump to document chunks.

### 5.5 Daily Review

- `开始今日复习` creates a session from the highest-priority reviewable mistakes.
- Phase 2 should support a focused review flow:
  - one mistake at a time
  - show question first
  - allow user to reveal answer/explanation
  - prompt for correction note
  - mark as mastered or needs another quiz
- Users can manually add/remove mistakes from today's queue.

### 5.6 Similar Practice and Re-Quiz

- `针对知识点再测` reuses the existing quiz generation endpoint with the mistake concept.
- `生成相似题` should create questions using the mistake's concept, topic, and possibly original question context.
- After retest completion, the relevant mistake can become `mastered` or remain `needs_requiz` depending on result.

### 5.7 Study Plan

- Use the existing study plan backend direction.
- User provides exam date and review horizon.
- The page shows a multi-day plan based on weak concepts and mistake counts.
- Plan items should link back to filtered mistake lists or concept retests.

### 5.8 Explanation Enhancement

- Where no explanation exists, use tracker wrong-answer explanation logic.
- Explanation should be split into:
  - why the correct answer is correct
  - why the user's answer was wrong
  - what to remember next time
- Phase 2 may generate this on demand to avoid unnecessary model calls.

### 5.9 Source and Export Enhancements

- Show source material name and chunk/page metadata when available.
- Later support jumping to a source excerpt.
- Support exporting selected mistakes as Markdown or CSV.
- Export includes question, wrong answer, correct answer, concept, topic, correction note, and status.

## 6. Backend Design

### 6.1 Existing Capabilities

Current backend already supports:

- recording mistakes through quiz submit scoring
- aggregating weak concepts
- generating study plans in tracker logic
- generating quizzes for a concept
- explaining wrong answers in tracker logic

### 6.2 New or Extended API Endpoints

`GET /api/review/mistakes`

- Returns paginated/filterable mistake records.
- Query parameters:
  - `status`
  - `concept`
  - `topic`
  - `question_type`
  - `search`
  - `sort`
  - `limit`
  - `offset`

`GET /api/review/mistakes/{id}`

- Returns one mistake detail.

`PATCH /api/review/mistakes/{id}`

- Updates:
  - `correction_note`
  - `status`
  - `mastered`

`POST /api/review/mistakes/{id}/similar-quiz`

- Generates similar questions from the mistake context.

`POST /api/review/daily-session`

- Builds or refreshes the daily review queue.

`POST /api/review/study-plan`

- Exposes the existing study plan capability to the frontend.

`POST /api/review/mistakes/{id}/explanation`

- Generates or refreshes explanation content on demand.

`GET /api/review/export`

- Exports selected or filtered mistakes in a simple downloadable format.

### 6.3 Mistake Data Shape

The frontend should receive mistake records with this shape:

```json
{
  "id": "string",
  "question_id": "string",
  "question_text": "string",
  "question_type": "multiple_choice",
  "concept": "string",
  "topic": "string",
  "wrong_answer": "string",
  "correct_answer": "string",
  "explanation": "string-or-null",
  "source_material": "string-or-null",
  "source_chunk_ids": ["string"],
  "status": "unreviewed",
  "attempt_count": 1,
  "last_wrong_at": "ISO datetime",
  "correction_note": "string-or-null",
  "mastered_at": "ISO datetime or null"
}
```

The public API uses `id` as a string so the frontend has a stable identifier contract. The backend may map this from an internal integer, UUID, or lightweight-store key. If the existing lightweight store lacks some fields at first, Phase 1 may return `null` for source/explanation fields and still complete the core loop.

### 6.4 Persistence Notes

Current tracker mistake records include:

- `user_id`
- `question_id`
- `concept`
- `topic`
- `wrong_answer`
- `correct_answer`

The implementation should extend the record shape without breaking old records. Missing fields should be handled gracefully.

Needed additions:

- `question_text`
- `question_type`
- `explanation`
- `source_material`
- `source_chunk_ids`
- `status`
- `attempt_count`
- `last_wrong_at`
- `correction_note`
- `mastered_at`

## 7. Frontend Design

### 7.1 Component Split

Replace the current single-purpose `DashboardCard` with review-focused components:

- `ReviewWorkbench`: top-level Review mode component.
- `ReviewSummaryBar`: compact metrics and global actions.
- `ReviewFilters`: status/search/concept/topic/type/sort controls.
- `WeakConceptList`: concept ranking and quick retest.
- `MistakeList`: filtered mistake records.
- `MistakeListItem`: one mistake row.
- `MistakeDetailPanel`: detail view and correction actions.
- `DailyReviewPanel` or `DailyReviewFlow`: Phase 2 focused review session.
- `StudyPlanDialog`: exam date and generated plan.
- `ReviewEmptyState`: empty states for no mistakes, no materials, or no quiz history.

### 7.2 State Management

Use local component state or a small review store if the state becomes shared across panels.

State needed:

- selected mistake id
- filter values
- search query
- sort value
- selected status tab
- loading and error states
- pending action id
- daily review queue
- study plan dialog state

### 7.3 API Client

Add `api.review` methods:

- `mistakes(params)`
- `mistake(id)`
- `updateMistake(id, payload)`
- `similarQuiz(id)`
- `dailySession(payload)`
- `studyPlan(payload)`
- `explainMistake(id)`
- `exportMistakes(params)`

### 7.4 Visual Direction

Keep the current restrained green academic/workbench style. Avoid a decorative marketing layout. The Review page should feel like a focused productivity surface:

- dense but readable
- clear status tags
- strong selected-row state
- no large empty hero region
- compact controls
- useful empty states

## 8. Data Flow

1. User enters Review mode.
2. Frontend fetches weak points and mistake list in parallel.
3. Default filter selects pending review items.
4. User selects a mistake.
5. Frontend fetches detail if list item does not already include enough data.
6. User writes correction note.
7. Frontend patches mistake status.
8. List and summary refresh.
9. User may generate retest or similar quiz.
10. Quiz completion updates mistake state or adds new mistakes through existing scoring flow.

## 9. Error Handling and Empty States

- If review data fails to load, show a retry state in the Review page.
- If no mistakes exist, show actions:
  - go to Quiz mode
  - upload material if no material exists
- If no records match filters, show `清除筛选`.
- If explanation generation fails, keep the mistake usable and show a retry button for that explanation only.
- If a status update fails, keep the previous UI state and show an inline error.

## 10. Accessibility and Responsiveness

- All action buttons have clear text labels.
- Selected mistake item uses both color and border/weight, not color alone.
- Filters are keyboard reachable.
- Mobile uses detail drawer/full screen instead of squeezing three columns.
- Long question text wraps cleanly without breaking the layout.

## 11. Phased Implementation Plan

### Phase 1: Core Mistake Book

Scope:

- backend mistake list/detail/update endpoints
- frontend review workbench layout
- mistake filters and search
- mistake detail panel
- correction note saving
- mark mastered / cancel mastered
- retest by concept
- empty/loading/error states

Acceptance criteria:

- A user can answer a quiz incorrectly, open Review mode, see the mistake, inspect it, save a correction, mark it mastered, and retest its concept.
- Default page is no longer mostly empty.
- Existing weak concept display remains available in the new layout.

Self-review before Phase 2:

- Verify API response handles older mistake records with missing fields.
- Verify no existing Quiz/Ask mode behavior regressed.
- Verify status transitions are clear and reversible where required.
- Run relevant backend and frontend tests.

### Phase 2: Guided Review and Remediation

Scope:

- daily review queue
- focused one-by-one review flow
- similar question generation
- on-demand wrong-answer explanation
- study plan UI connected to backend
- review session completion summary

Acceptance criteria:

- A user can click `开始今日复习`, move through a queue, reveal answers/explanations, write notes, and finish with a summary.
- A user can generate similar practice for a mistake.
- A user can generate and view a multi-day study plan.

Self-review before Phase 3:

- Verify session queue priority matches product rules.
- Verify generated content failures do not block manual review.
- Verify Quiz mode handoff works for retests/similar practice.
- Run relevant backend and frontend tests.

### Phase 3: Long-Term Review Intelligence

Scope:

- basic spaced-review scheduling fields
- mastery trend indicators
- source excerpt/source jump foundation
- export selected/filtered mistakes
- improved review history/status timeline

Acceptance criteria:

- The page can show what should be reviewed again later.
- Users can export their mistake book.
- Source metadata is useful even if full document viewing remains basic.
- Mastery progress is visible beyond a single correction action.

Self-review before final report:

- Verify advanced fields degrade gracefully for old records.
- Verify export content matches visible filtered data.
- Verify mobile layout remains usable.
- Run full available verification suite or clearly report unavailable checks.

## 12. Testing Strategy

Backend:

- tests for mistake list filtering
- tests for mistake detail
- tests for updating correction/status/mastery
- tests for old records missing optional fields
- tests for daily session prioritization
- tests for study plan API

Frontend:

- component tests for Review workbench states
- tests for filtering/search behavior
- tests for detail selection and correction save
- tests for mark mastered/cancel mastered
- tests for empty and error states
- tests for retest handoff into Quiz mode

End-to-end:

- create or seed a mistake
- open Review mode
- filter/select mistake
- save correction
- mark mastered
- generate retest

## 13. Risks and Mitigations

- Risk: existing mistake records are too sparse for detail view.
  - Mitigation: show known fields first; store richer fields for new mistakes; handle missing values explicitly.

- Risk: too many Phase 2/3 features make the first release slow.
  - Mitigation: Phase 1 focuses on the core mistake-book loop; later phases build on that foundation.

- Risk: AI-generated explanations may fail or be slow.
  - Mitigation: generate explanations on demand and keep manual review usable without them.

- Risk: Review mode becomes visually crowded.
  - Mitigation: use compact filters, clear selection states, and a mobile detail drawer.

## 14. Approval Gate

No implementation should begin until the user confirms this document. After approval, the next step is to create a detailed implementation plan and then execute Phase 1, Phase 2, and Phase 3 in order, with self-review after each phase.

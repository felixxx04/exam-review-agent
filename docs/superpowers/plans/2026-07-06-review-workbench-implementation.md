# Review Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three-phase Review Workbench so users can browse, correct, retest, schedule, and export mistake records.

**Architecture:** Extend the existing lightweight review backend around `DictStore` and `TrackerAgent`, then replace the current `DashboardCard` Review UI with focused review-workbench components. Keep the implementation compatible with older sparse mistake records while storing richer fields for new quiz mistakes.

**Tech Stack:** FastAPI, dataclass schemas, existing in-memory `DictStore`, Next.js 15, React 19, Zustand, Vitest, pytest.

---

## File Structure

- Modify `backend/app/core/store.py`: add query/update helpers needed for mistake records.
- Modify `backend/app/agents/tracker_agent.py`: store richer mistake records and add review-specific helpers.
- Modify `backend/app/schemas/quiz.py`: accept question context during quiz submit.
- Modify `backend/app/api/quiz.py`: pass question context into tracker scoring.
- Modify `backend/app/schemas/review.py`: add mistake, daily session, explanation, export, and plan schemas.
- Modify `backend/app/api/review.py`: expose Phase 1-3 review endpoints.
- Modify `backend/tests/test_tracker_agent.py`: cover richer mistake records and helper behavior.
- Modify `backend/tests/test_api/test_review.py`: cover review API list/detail/update/session/export.
- Modify `frontend/src/types/index.ts`: add review workbench types.
- Modify `frontend/src/lib/api.ts`: add review API methods and extended quiz submit payload.
- Modify `frontend/src/components/QuizCard.tsx`: submit question context so wrong answers become useful mistakes.
- Replace `frontend/src/components/DashboardCard.tsx`: render the new workbench shell while preserving export name.
- Create `frontend/src/components/review/ReviewWorkbench.tsx`: top-level Review mode component.
- Create `frontend/src/components/review/ReviewSummaryBar.tsx`: metrics and global actions.
- Create `frontend/src/components/review/ReviewFilters.tsx`: status/search/filter/sort controls.
- Create `frontend/src/components/review/WeakConceptList.tsx`: weak concept ranking and retest actions.
- Create `frontend/src/components/review/MistakeList.tsx`: selectable mistake list.
- Create `frontend/src/components/review/MistakeDetailPanel.tsx`: detail, correction, mastery, explanation, export/source actions.
- Create `frontend/src/components/review/DailyReviewFlow.tsx`: Phase 2 focused review flow.
- Create `frontend/src/components/review/StudyPlanDialog.tsx`: Phase 2 study-plan UI.
- Create `frontend/src/components/review/ReviewExportPanel.tsx`: Phase 3 export controls.
- Create `frontend/src/components/review/reviewUtils.ts`: status labels, priority sorting, filtering helpers.
- Create `frontend/src/__tests__/components/ReviewWorkbench.test.tsx`: core UI behavior.
- Modify `.gitignore`: ignore `.superpowers/` local brainstorming artifacts.

---

## Phase 1: Core Mistake Book

### Task 1: Backend Store and Tracker Foundations

**Files:**
- Modify: `backend/app/core/store.py`
- Modify: `backend/app/agents/tracker_agent.py`
- Test: `backend/tests/test_tracker_agent.py`

- [ ] **Step 1: Write tests for richer mistake recording**

Add tests that call `TrackerAgent.score_answer()` with `question_text`, `explanation`, and `source_chunk_ids`, then assert the stored mistake contains:

```python
assert call_args["type"] == "mistake_records"
assert call_args["question_text"] == "题干"
assert call_args["question_type"] == "multiple_choice"
assert call_args["status"] == "unreviewed"
assert call_args["attempt_count"] == 1
assert call_args["correction_note"] == ""
assert call_args["mastered_at"] is None
```

- [ ] **Step 2: Run tracker tests and confirm failure**

Run: `cd backend; .venv\Scripts\python.exe -m pytest tests/test_tracker_agent.py -q`

Expected: failure because `score_answer()` does not yet accept/store the richer fields.

- [ ] **Step 3: Extend `DictStore` safely**

Add helpers:

```python
async def all(self) -> list[dict]:
    return list(self._records)

async def update(self, predicate, updates: dict) -> dict | None:
    for record in self._records:
        if predicate(record):
            record.update(updates)
            return record
    return None
```

- [ ] **Step 4: Extend `TrackerAgent.score_answer()`**

Add optional parameters:

```python
question_text: str = "",
explanation: str = "",
source_chunk_ids: list[str] | None = None,
source_material: str | None = None,
```

Store defaulted fields when the answer is wrong:

```python
"question_text": question_text,
"question_type": question_type,
"explanation": explanation,
"source_chunk_ids": source_chunk_ids or [],
"source_material": source_material,
"status": "unreviewed",
"attempt_count": 1,
"last_wrong_at": datetime.now(timezone.utc).isoformat(),
"correction_note": "",
"mastered_at": None,
"review_history": [],
"next_review_at": None,
```

- [ ] **Step 5: Run tracker tests**

Run: `cd backend; .venv\Scripts\python.exe -m pytest tests/test_tracker_agent.py -q`

Expected: pass.

### Task 2: Phase 1 Review API

**Files:**
- Modify: `backend/app/schemas/review.py`
- Modify: `backend/app/api/review.py`
- Test: `backend/tests/test_api/test_review.py`

- [ ] **Step 1: Write API tests**

Cover:

```python
response = await client.get("/api/review/mistakes")
assert response.status_code == 200

patch = await client.patch(
    "/api/review/mistakes/q1",
    json={"correction_note": "记住定义", "status": "corrected"},
)
assert patch.json()["data"]["status"] == "corrected"
```

- [ ] **Step 2: Add schemas**

Add dataclasses/request models for:

```python
class MistakeUpdateRequest(BaseModel):
    correction_note: str | None = None
    status: str | None = None
    mastered: bool | None = None

@dataclass
class MistakeRecord:
    id: str
    question_id: str
    question_text: str
    question_type: str
    concept: str
    topic: str
    wrong_answer: str
    correct_answer: str
    explanation: str | None = None
    source_material: str | None = None
    source_chunk_ids: list[str] = field(default_factory=list)
    status: str = "unreviewed"
    attempt_count: int = 1
    last_wrong_at: str = ""
    correction_note: str = ""
    mastered_at: str | None = None
    next_review_at: str | None = None
```

- [ ] **Step 3: Implement list/detail/update endpoints**

Implement:

```python
GET /api/review/mistakes
GET /api/review/mistakes/{mistake_id}
PATCH /api/review/mistakes/{mistake_id}
```

Filtering supports `status`, `concept`, `topic`, `question_type`, `search`, `sort`, `limit`, and `offset`.

- [ ] **Step 4: Run review API tests**

Run: `cd backend; .venv\Scripts\python.exe -m pytest tests/test_api/test_review.py -q`

Expected: pass.

### Task 3: Quiz Submit Context

**Files:**
- Modify: `backend/app/schemas/quiz.py`
- Modify: `backend/app/api/quiz.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/QuizCard.tsx`
- Test: `backend/tests/test_api/test_quiz.py`
- Test: `frontend/src/__tests__/components/QuizCard.test.tsx`

- [ ] **Step 1: Add backend test for contextual submit**

Submit a wrong answer with `question_text`, `concept`, `topic`, `explanation`, and `source_chunk_ids`; assert the response still returns `mistake_recorded: true`.

- [ ] **Step 2: Change submit API to accept a JSON body**

Keep query-parameter compatibility, but prefer a request body:

```python
class QuizSubmitRequest(BaseModel):
    question_id: str
    correct_answer: str
    student_answer: str
    question_type: str = "multiple_choice"
    concept: str = ""
    topic: str = ""
    question_text: str = ""
    explanation: str = ""
    source_chunk_ids: list[str] = []
```

- [ ] **Step 3: Update frontend submit call**

Call:

```ts
api.quiz.submit({
  questionId: q.id,
  correctAnswer: q.correct,
  studentAnswer: selected,
  questionType: q.question_type,
  concept: q.topic,
  topic: q.topic,
  questionText: q.question,
  explanation: q.explanation ?? "",
  sourceChunkIds: q.source_chunk_ids,
})
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
cd backend; .venv\Scripts\python.exe -m pytest tests/test_api/test_quiz.py tests/test_api/test_review.py -q
cd frontend; npm test -- --run src/__tests__/components/QuizCard.test.tsx
```

Expected: pass.

### Task 4: Frontend Core Workbench

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/DashboardCard.tsx`
- Create: `frontend/src/components/review/ReviewWorkbench.tsx`
- Create: `frontend/src/components/review/ReviewSummaryBar.tsx`
- Create: `frontend/src/components/review/ReviewFilters.tsx`
- Create: `frontend/src/components/review/WeakConceptList.tsx`
- Create: `frontend/src/components/review/MistakeList.tsx`
- Create: `frontend/src/components/review/MistakeDetailPanel.tsx`
- Create: `frontend/src/components/review/reviewUtils.ts`
- Test: `frontend/src/__tests__/components/ReviewWorkbench.test.tsx`

- [ ] **Step 1: Add review types and API client methods**

Add `ReviewMistake`, `ReviewMistakeStatus`, `MistakeListData`, and `ReviewSummary`.

Add:

```ts
api.review.mistakes(params)
api.review.mistake(id)
api.review.updateMistake(id, payload)
```

- [ ] **Step 2: Create UI tests**

Render `ReviewWorkbench`, mock `api.review.weakPoints` and `api.review.mistakes`, and assert:

```ts
expect(screen.getByText("待复习错题")).toBeInTheDocument();
expect(screen.getByText("保存订正")).toBeInTheDocument();
```

- [ ] **Step 3: Implement workbench shell**

`DashboardCard` should become:

```tsx
export function DashboardCard() {
  const { mode } = useChatStore();
  if (mode !== "review") return null;
  return <ReviewWorkbench />;
}
```

- [ ] **Step 4: Implement correction and mastery actions**

`MistakeDetailPanel` calls `api.review.updateMistake` for:

```ts
{ correction_note: note, status: "corrected" }
{ mastered: true }
{ mastered: false }
```

- [ ] **Step 5: Run frontend focused tests**

Run: `cd frontend; npm test -- --run src/__tests__/components/ReviewWorkbench.test.tsx`

Expected: pass.

### Phase 1 Self-Review

- [ ] Confirm older mistake records render with fallback text.
- [ ] Confirm Review mode is no longer mostly blank.
- [ ] Confirm retesting a concept switches to Quiz mode.
- [ ] Run:

```powershell
cd backend; .venv\Scripts\python.exe -m pytest tests/test_tracker_agent.py tests/test_api/test_quiz.py tests/test_api/test_review.py -q
cd frontend; npm test -- --run src/__tests__/components/QuizCard.test.tsx src/__tests__/components/ReviewWorkbench.test.tsx
```

---

## Phase 2: Guided Review and Remediation

### Task 5: Daily Review Backend and UI

**Files:**
- Modify: `backend/app/schemas/review.py`
- Modify: `backend/app/api/review.py`
- Create: `frontend/src/components/review/DailyReviewFlow.tsx`
- Modify: `frontend/src/components/review/ReviewWorkbench.tsx`
- Test: `backend/tests/test_api/test_review.py`
- Test: `frontend/src/__tests__/components/ReviewWorkbench.test.tsx`

- [ ] **Step 1: Add daily session endpoint**

`POST /api/review/daily-session` returns the highest-priority reviewable mistakes:

```json
{
  "mistakes": [],
  "total": 0,
  "message": "今日复习已准备好"
}
```

- [ ] **Step 2: Add focused review flow**

The flow shows one mistake at a time with:

```text
题目 -> 显示答案 -> 写订正 -> 标记掌握/需要再测 -> 下一题
```

- [ ] **Step 3: Run focused tests**

Run backend and frontend review tests from Phase 1 self-review.

### Task 6: Similar Quiz and Explanation

**Files:**
- Modify: `backend/app/api/review.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/review/MistakeDetailPanel.tsx`
- Test: `backend/tests/test_api/test_review.py`
- Test: `frontend/src/__tests__/components/ReviewWorkbench.test.tsx`

- [ ] **Step 1: Add similar quiz endpoint**

`POST /api/review/mistakes/{id}/similar-quiz` returns quiz payload generated with mistake concept/topic.

- [ ] **Step 2: Add explanation endpoint**

`POST /api/review/mistakes/{id}/explanation` returns and stores an explanation string.

- [ ] **Step 3: Wire frontend buttons**

`生成相似题` moves to Quiz mode with generated questions.

`生成错因分析` updates only the selected detail panel.

- [ ] **Step 4: Run focused tests**

Run review API and ReviewWorkbench tests.

### Task 7: Study Plan Dialog

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/review/StudyPlanDialog.tsx`
- Modify: `frontend/src/components/review/ReviewWorkbench.tsx`
- Test: `frontend/src/__tests__/components/ReviewWorkbench.test.tsx`

- [ ] **Step 1: Add frontend study plan API**

Call existing `POST /api/review/study-plan`.

- [ ] **Step 2: Implement dialog**

Fields:

```text
考试日期
复习天数
生成计划
```

Render returned day-by-day topics and tasks.

- [ ] **Step 3: Run focused tests**

Run ReviewWorkbench tests.

### Phase 2 Self-Review

- [ ] Confirm generated-content failures do not block manual review.
- [ ] Confirm daily session can be completed with a summary.
- [ ] Confirm similar quiz handoff reaches Quiz mode.
- [ ] Run focused backend/frontend tests.

---

## Phase 3: Long-Term Review Intelligence

### Task 8: Scheduling, Trends, and History

**Files:**
- Modify: `backend/app/api/review.py`
- Modify: `frontend/src/components/review/MistakeDetailPanel.tsx`
- Modify: `frontend/src/components/review/ReviewSummaryBar.tsx`
- Test: `backend/tests/test_api/test_review.py`
- Test: `frontend/src/__tests__/components/ReviewWorkbench.test.tsx`

- [ ] **Step 1: Add review history updates**

When status changes, append records like:

```json
{ "event": "mastered", "at": "ISO datetime" }
```

- [ ] **Step 2: Add next review scheduling**

Set `next_review_at` when users mark `needs_requiz` or `corrected`.

- [ ] **Step 3: Show trend indicators**

Display:

```text
已掌握
待复习
下次复习
订正次数
```

### Task 9: Source Metadata and Export

**Files:**
- Modify: `backend/app/api/review.py`
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/review/ReviewExportPanel.tsx`
- Modify: `frontend/src/components/review/MistakeDetailPanel.tsx`
- Test: `backend/tests/test_api/test_review.py`
- Test: `frontend/src/__tests__/components/ReviewWorkbench.test.tsx`

- [ ] **Step 1: Add export endpoint**

`GET /api/review/export?format=markdown` returns:

```text
# 错题导出

## 题目
...
```

`format=csv` returns CSV text.

- [ ] **Step 2: Add frontend export panel**

Allow export of current filtered set as Markdown or CSV.

- [ ] **Step 3: Improve source display**

Show source material and chunk ids in the detail panel. If there is no source, show `暂无来源信息`.

### Phase 3 Self-Review

- [ ] Confirm export content matches current visible filters.
- [ ] Confirm source metadata degrades gracefully.
- [ ] Confirm mobile layout still works after added controls.
- [ ] Run full available verification:

```powershell
cd backend; .venv\Scripts\python.exe -m pytest tests/test_tracker_agent.py tests/test_api/test_quiz.py tests/test_api/test_review.py -q
cd frontend; npm test -- --run src/__tests__/components/QuizCard.test.tsx src/__tests__/components/ReviewWorkbench.test.tsx
```

---

## Execution Choice

The user requested automatic execution after approving the design. Use inline execution in this session with phase checkpoints:

1. Execute Phase 1 tasks.
2. Self-review and verify Phase 1.
3. Execute Phase 2 tasks.
4. Self-review and verify Phase 2.
5. Execute Phase 3 tasks.
6. Self-review and produce the final report.

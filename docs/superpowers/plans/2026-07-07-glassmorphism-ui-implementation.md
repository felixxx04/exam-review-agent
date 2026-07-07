# Glassmorphism UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved glassmorphism design system for the existing AI learning workspace without changing backend APIs, stores, upload flow, quiz scoring, or review data logic.

**Architecture:** Keep the current Next.js component structure and concentrate visual behavior in `frontend/src/app/globals.css` through semantic CSS tokens and reusable classes. Make small JSX changes only where inline styles block consistent glass states or where components need stable class hooks for mode-specific styling.

**Tech Stack:** Next.js 15 App Router, React 19, Tailwind CSS v4 import, plain CSS tokens in `globals.css`, lucide-react icons, Vitest component tests, Playwright/Edge screenshots for visual verification.

---

## File Structure

- Modify: `frontend/src/app/globals.css`
  - Owns design tokens, glass utilities, app shell, sidebar, header, quick actions, chat, quiz, review, motion, responsive rules, reduced-motion behavior.
- Modify: `frontend/src/components/MessageList.tsx`
  - Adds stable role/data attributes and class hooks for user/assistant bubbles and citation chips while preserving message rendering.
- Modify: `frontend/src/components/QuizCard.tsx`
  - Replaces blocking inline visual styling on quiz shell, option buttons, explanation, and navigation with class hooks plus CSS variables for answer state.
- Modify: `frontend/src/components/review/ReviewSummaryBar.tsx`
  - Adds class hooks for summary panel, metric chips, and action buttons.
- Modify: `frontend/src/components/review/ReviewFilters.tsx`
  - Adds class hooks for filter buttons, inputs, and selects.
- Modify: `frontend/src/components/review/WeakConceptList.tsx`
  - Adds class hooks for weak concept cards and retest actions.
- Modify: `frontend/src/components/review/MistakeList.tsx`
  - Adds class hooks and data-selected state for mistake rows.
- Modify: `frontend/src/components/review/MistakeDetailPanel.tsx`
  - Adds class hooks for detail panel, answer blocks, metadata blocks, and action buttons.
- Modify: `frontend/src/components/review/ReviewExportPanel.tsx`
  - Adds glass panel and button hooks for export actions.
- Modify: `frontend/src/components/review/DailyReviewFlow.tsx`
  - Aligns daily review panel, reveal button, textarea, and actions with the glass system.
- Modify: `frontend/src/components/review/StudyPlanDialog.tsx`
  - Aligns scrim and dialog panel with glass z-index and radius tokens.
- Modify: `frontend/src/__tests__/components/Header.test.tsx`, `AppSidebar.test.tsx`, `ChatInput.test.tsx`, `MessageList.test.tsx`, `QuizCard.test.tsx`, `ReviewWorkbench.test.tsx`, `StudyPlanDialog.test.tsx`
  - Update only if class hooks or accessible names change. Do not weaken behavior assertions.

## Task 1: Baseline And Guardrails

**Files:**
- Read: `docs/superpowers/specs/2026-07-07-glassmorphism-ui-design.md`
- Read: `frontend/src/app/globals.css`
- Read: `frontend/src/components/MessageList.tsx`
- Read: `frontend/src/components/QuizCard.tsx`
- Read: `frontend/src/components/review/*.tsx`

- [ ] **Step 1: Confirm working tree and isolate the UI work**

Run:

```powershell
git status --short
git branch --show-current
```

Expected: existing unrelated backend/frontend changes may be present. Do not revert them. If not already on a UI branch, create one before implementation:

```powershell
git switch -c codex/glassmorphism-ui
```

- [ ] **Step 2: Run current focused checks**

Run:

```powershell
cd D:\ai-agent\frontend
npm test -- --run src/__tests__/components/Header.test.tsx src/__tests__/components/AppSidebar.test.tsx src/__tests__/components/ChatInput.test.tsx src/__tests__/components/MessageList.test.tsx src/__tests__/components/QuizCard.test.tsx src/__tests__/components/ReviewWorkbench.test.tsx src/__tests__/components/StudyPlanDialog.test.tsx
```

Expected: component tests pass before visual work begins. If a test fails because of pre-existing unrelated changes, capture the failure and continue only after identifying whether the failing file is touched by this plan.

- [ ] **Step 3: Run production build baseline**

Run:

```powershell
cd D:\ai-agent\frontend
npm run build
```

Expected: build passes. This gives a baseline for later CSS and JSX changes.

- [ ] **Step 4: Commit only if a branch was created with no file changes**

No code commit is needed for this task unless the branch creation must be recorded in the app via branch directive at the end of the implementation session.

## Task 2: Glass Design Tokens And Foundation Utilities

**Files:**
- Modify: `frontend/src/app/globals.css`

- [ ] **Step 1: Add semantic glass tokens to `:root`**

In `frontend/src/app/globals.css`, extend the existing `:root` block with these tokens after the current color tokens:

```css
  /* Glassmorphism palette */
  --color-bg: #f8fbff;
  --color-panel: rgb(255 255 255 / 0.78);
  --color-surface: rgb(255 255 255 / 0.74);
  --color-surface-raised: rgb(255 255 255 / 0.82);
  --color-surface-hover: rgb(255 255 255 / 0.9);
  --color-ink: #0f172a;
  --color-muted: #5f6f86;
  --color-soft: #8aa0ba;
  --color-primary: #2563eb;
  --color-primary-hover: #1d4ed8;
  --color-primary-subtle: rgb(219 234 254 / 0.62);
  --color-accent: #0ea5e9;
  --color-accent-hover: #0284c7;
  --color-accent-subtle: rgb(207 250 254 / 0.58);
  --color-purple: #8b5cf6;
  --color-purple-subtle: rgb(237 233 254 / 0.58);
  --color-border: rgb(255 255 255 / 0.72);
  --color-border-strong: rgb(148 163 184 / 0.34);
  --color-focus-ring: rgb(14 165 233 / 0.24);

  /* Glass layers */
  --glass-bg-strong: rgb(255 255 255 / 0.58);
  --glass-bg-medium: rgb(255 255 255 / 0.68);
  --glass-bg-soft: rgb(255 255 255 / 0.78);
  --glass-bg-readable: rgb(255 255 255 / 0.84);
  --glass-border: rgb(255 255 255 / 0.76);
  --glass-border-strong: rgb(255 255 255 / 0.92);
  --glass-blur-strong: 24px;
  --glass-blur-medium: 16px;
  --glass-blur-soft: 10px;
  --glass-shadow-soft: 0 14px 36px rgb(60 80 160 / 0.12);
  --glass-shadow-float: 0 26px 80px rgb(60 80 160 / 0.18);
  --glow-blue: 0 0 0 1px rgb(37 99 235 / 0.18), 0 18px 46px rgb(37 99 235 / 0.18);
  --glow-cyan: 0 0 0 1px rgb(14 165 233 / 0.22), 0 18px 46px rgb(14 165 233 / 0.16);
  --glow-purple: 0 0 0 1px rgb(139 92 246 / 0.18), 0 18px 46px rgb(139 92 246 / 0.14);

  /* Radius */
  --radius-sm: 0.5rem;
  --radius-md: 0.75rem;
  --radius-lg: 1rem;
  --radius-xl: 1.5rem;
  --radius-float: 1.875rem;
  --radius-panel: 1.25rem;
  --radius-control: 0.875rem;
  --radius-pill: 9999px;
  --radius-full: 9999px;

  /* Layering */
  --z-background: 0;
  --z-content: 10;
  --z-navigation: 20;
  --z-input: 30;
  --z-scrim: 50;
  --z-dialog: 60;
  --z-toast: 70;

  /* Motion */
  --motion-glass: 280ms cubic-bezier(0.22, 1, 0.36, 1);
```

Keep existing typography, spacing, and layout tokens unless they conflict with the above.

- [ ] **Step 2: Add glass utility classes**

Add these reusable classes after the utility class section:

```css
.glass-strong,
.glass-medium,
.glass-soft,
.glass-readable {
  border: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow-soft), inset 0 1px 0 rgb(255 255 255 / 0.66);
}

.glass-strong {
  background: var(--glass-bg-strong);
  backdrop-filter: blur(var(--glass-blur-strong)) saturate(1.22);
}

.glass-medium {
  background: var(--glass-bg-medium);
  backdrop-filter: blur(var(--glass-blur-medium)) saturate(1.16);
}

.glass-soft {
  background: var(--glass-bg-soft);
  backdrop-filter: blur(var(--glass-blur-soft)) saturate(1.08);
}

.glass-readable {
  background: var(--glass-bg-readable);
  backdrop-filter: blur(var(--glass-blur-soft)) saturate(1.04);
}

.glass-pill {
  border-radius: var(--radius-pill);
}

.glass-float {
  border-radius: var(--radius-float);
  box-shadow: var(--glass-shadow-float), inset 0 1px 0 rgb(255 255 255 / 0.72);
}
```

- [ ] **Step 3: Add fallback for browsers without backdrop filter**

Add this after the utility classes:

```css
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .glass-strong,
  .glass-medium,
  .glass-soft,
  .glass-readable,
  .app-sidebar,
  .app-header,
  .chat-input-shell,
  .quick-card,
  .review-panel {
    background: rgb(255 255 255 / 0.94);
  }
}
```

- [ ] **Step 4: Verify formatting**

Run:

```powershell
cd D:\ai-agent\frontend
npx prettier --check src/app/globals.css
```

Expected: pass after formatting. If it fails, run:

```powershell
npx prettier --write src/app/globals.css
```

- [ ] **Step 5: Commit token foundation**

Run:

```powershell
git add frontend/src/app/globals.css
git commit -m "style: add glassmorphism design tokens"
```

Expected: one commit containing only `globals.css` token and utility changes.

## Task 3: App Background, Sidebar, Header, And Buttons

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify only if needed: `frontend/src/components/Header.tsx`
- Modify only if needed: `frontend/src/components/AppSidebar.tsx`

- [ ] **Step 1: Replace app background with low-saturation aurora cloud**

In `globals.css`, replace `.app-shell` background with:

```css
.app-shell {
  position: relative;
  isolation: isolate;
  display: grid;
  grid-template-columns: var(--sidebar-w) minmax(0, 1fr);
  height: 100dvh;
  max-height: 100dvh;
  overflow: hidden;
  background:
    radial-gradient(circle at 12% 8%, rgb(96 165 250 / 0.34), transparent 30rem),
    radial-gradient(circle at 84% 14%, rgb(139 92 246 / 0.28), transparent 31rem),
    radial-gradient(circle at 58% 88%, rgb(20 184 166 / 0.2), transparent 30rem),
    linear-gradient(135deg, #fbfdff 0%, #eaf6ff 46%, #f8f0ff 100%);
}

.app-shell::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: var(--z-background);
  pointer-events: none;
  background:
    linear-gradient(120deg, rgb(255 255 255 / 0.36), transparent 42%),
    linear-gradient(180deg, rgb(255 255 255 / 0.28), rgb(255 255 255 / 0));
}
```

Keep app content above the pseudo-element:

```css
.app-sidebar,
.app-main {
  position: relative;
}
```

- [ ] **Step 2: Convert sidebar to strong glass navigation**

Update `.app-sidebar`:

```css
.app-sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  min-width: 0;
  overflow-y: auto;
  border-right: 1px solid var(--glass-border);
  background: var(--glass-bg-strong);
  backdrop-filter: blur(var(--glass-blur-strong)) saturate(1.2);
  box-shadow: var(--glass-shadow-soft), inset -1px 0 0 rgb(255 255 255 / 0.55);
  padding: var(--space-5) var(--space-4);
  z-index: var(--z-navigation);
}
```

Update active rows:

```css
.sidebar-row[data-active="true"],
.material-row[data-active="true"] {
  background: linear-gradient(135deg, rgb(219 234 254 / 0.72), rgb(207 250 254 / 0.48));
  border-color: rgb(37 99 235 / 0.28);
  box-shadow: inset 3px 0 0 var(--color-primary), var(--glow-blue);
}
```

- [ ] **Step 3: Convert header and mode control to glass segmented controls**

Update `.app-header`, `.mode-pill-nav`, `.mode-pill`, `.primary-action`:

```css
.app-header {
  height: var(--header-h);
  flex: 0 0 var(--header-h);
  border-bottom: 1px solid var(--glass-border);
  background: var(--glass-bg-strong);
  backdrop-filter: blur(var(--glass-blur-strong)) saturate(1.18);
  box-shadow: var(--glass-shadow-soft), inset 0 -1px 0 rgb(255 255 255 / 0.56);
  z-index: var(--z-navigation);
}

.mode-pill-nav {
  display: flex;
  gap: 0.25rem;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-pill);
  background: rgb(255 255 255 / 0.5);
  box-shadow: var(--glass-shadow-soft), inset 0 1px 0 rgb(255 255 255 / 0.7);
  padding: 0.25rem;
  backdrop-filter: blur(var(--glass-blur-medium)) saturate(1.12);
}

.mode-pill {
  border-radius: var(--radius-pill);
  min-height: 2.5rem;
}

.mode-pill[data-active="true"],
.primary-action,
.sidebar-upload-button,
.quick-card-button {
  background: linear-gradient(135deg, var(--color-primary), var(--color-accent));
  color: white;
  box-shadow: var(--glow-blue);
}
```

- [ ] **Step 4: Verify header and sidebar tests still pass**

Run:

```powershell
cd D:\ai-agent\frontend
npm test -- --run src/__tests__/components/Header.test.tsx src/__tests__/components/AppSidebar.test.tsx
```

Expected: both test files pass. If accessible button names changed, update tests to assert the new accessible names, not visual class names.

- [ ] **Step 5: Commit navigation glass layer**

Run:

```powershell
git add frontend/src/app/globals.css frontend/src/components/Header.tsx frontend/src/components/AppSidebar.tsx frontend/src/__tests__/components/Header.test.tsx frontend/src/__tests__/components/AppSidebar.test.tsx
git commit -m "style: apply glass navigation shell"
```

Expected: commit includes only navigation/header/sidebar-related changes.

## Task 4: Ask Mode, Quick Actions, Chat Input, And Message Bubbles

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/components/MessageList.tsx`
- Test: `frontend/src/__tests__/components/MessageList.test.tsx`
- Test: `frontend/src/__tests__/components/ChatInput.test.tsx`

- [ ] **Step 1: Add class hooks to message bubbles**

In `MessageList.tsx`, change the message bubble wrapper from the inline style-driven class to a data-role class. Preserve existing content and citations.

Use this JSX shape for the message bubble `div`:

```tsx
<div
  className="message-bubble"
  data-role={isUser ? "user" : "assistant"}
  data-streaming={showCursor}
>
```

Move current inline visual properties to CSS. Keep only the dynamic rendering logic for `showThinking`, `showCursor`, and citations.

For citation chips, use:

```tsx
<span
  key={ci}
  className="citation-chip"
  data-role={isUser ? "user" : "assistant"}
>
  {c.source}
  {c.page ? ` P.${c.page}` : ""}
</span>
```

- [ ] **Step 2: Add glass message CSS**

Add this to `globals.css` near message styles:

```css
.message-bubble {
  max-width: 85%;
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-base);
  line-height: var(--leading-prose);
  box-shadow: var(--glass-shadow-soft);
  transition:
    transform var(--motion-glass),
    box-shadow var(--motion-glass),
    border-color var(--motion-glass);
}

.message-bubble[data-role="user"] {
  border: 1px solid rgb(37 99 235 / 0.32);
  border-radius: var(--radius-float) var(--radius-float) var(--radius-md) var(--radius-float);
  background: linear-gradient(135deg, rgb(37 99 235 / 0.9), rgb(14 165 233 / 0.84));
  color: white;
  backdrop-filter: blur(var(--glass-blur-soft)) saturate(1.08);
}

.message-bubble[data-role="assistant"] {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-float) var(--radius-float) var(--radius-float) var(--radius-md);
  background: var(--glass-bg-readable);
  color: var(--color-ink);
  backdrop-filter: blur(var(--glass-blur-soft)) saturate(1.04);
}

.citation-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  border-radius: var(--radius-pill);
  border: 1px solid rgb(255 255 255 / 0.72);
  padding: 0.125rem 0.5rem;
  font-size: var(--text-xs);
}

.citation-chip[data-role="assistant"] {
  background: var(--color-primary-subtle);
  color: var(--color-primary);
}

.citation-chip[data-role="user"] {
  background: rgb(255 255 255 / 0.18);
  color: white;
}
```

- [ ] **Step 3: Convert quick actions and chat input to floating glass**

Update CSS:

```css
.quick-card {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-float);
  background: var(--glass-bg-medium);
  backdrop-filter: blur(var(--glass-blur-medium)) saturate(1.14);
  box-shadow: var(--glass-shadow-float), inset 0 1px 0 rgb(255 255 255 / 0.68);
}

.quick-card:hover {
  border-color: rgb(14 165 233 / 0.34);
  box-shadow: var(--glass-shadow-float), var(--glow-cyan);
  transform: translateY(-4px);
}

.chat-input-dock {
  z-index: var(--z-input);
  background: linear-gradient(180deg, rgb(248 251 255 / 0), rgb(248 251 255 / 0.78) 34%);
}

.chat-input-shell {
  border: 1px solid var(--glass-border-strong);
  border-radius: var(--radius-pill);
  background: var(--glass-bg-strong);
  backdrop-filter: blur(var(--glass-blur-strong)) saturate(1.18);
  box-shadow: var(--glass-shadow-float), inset 0 1px 0 rgb(255 255 255 / 0.72);
}

.chat-input-shell:focus-within {
  border-color: rgb(14 165 233 / 0.44);
  box-shadow: var(--glass-shadow-float), var(--glow-cyan), var(--glow-purple);
}

.chat-send-button {
  border-radius: var(--radius-pill);
  background: linear-gradient(135deg, var(--color-primary), var(--color-accent));
  box-shadow: var(--glow-blue);
}
```

- [ ] **Step 4: Run ask mode tests**

Run:

```powershell
cd D:\ai-agent\frontend
npm test -- --run src/__tests__/components/MessageList.test.tsx src/__tests__/components/ChatInput.test.tsx
```

Expected: tests pass with existing behavior.

- [ ] **Step 5: Commit ask mode glass UI**

Run:

```powershell
git add frontend/src/app/globals.css frontend/src/components/MessageList.tsx frontend/src/__tests__/components/MessageList.test.tsx frontend/src/__tests__/components/ChatInput.test.tsx
git commit -m "style: add glass ask mode experience"
```

Expected: commit focuses on quick actions, chat input, and messages.

## Task 5: Quiz Mode Glass Focus State

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/components/QuizCard.tsx`
- Test: `frontend/src/__tests__/components/QuizCard.test.tsx`

- [ ] **Step 1: Add quiz-specific class hooks**

In `QuizCard.tsx`, use class hooks for the root scroll area, question card, option buttons, explanation block, submit button, and navigation buttons.

For the root:

```tsx
<div className="quiz-workspace flex-1 overflow-y-auto px-5 py-4">
```

For the question card:

```tsx
<div className="quiz-question-card">
```

For each option button:

```tsx
<button
  key={i}
  onClick={() => !isSubmitted && answerQuestion(q.id, optionState.letter)}
  disabled={isSubmitted}
  className="quiz-option"
  data-selected={optionState.isSelected}
  data-correct={optionState.isCorrect}
  data-wrong={optionState.isWrong}
  style={{
    "--quiz-option-bg": optionState.background,
    "--quiz-option-border": optionState.border,
    "--quiz-option-color": optionState.textColor,
  } as React.CSSProperties}
>
```

Preserve the `CheckCircle2` and `XCircle` icons.

- [ ] **Step 2: Add quiz CSS**

Add:

```css
.quiz-workspace {
  background: linear-gradient(180deg, rgb(255 255 255 / 0.28), transparent);
}

.quiz-question-card {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-float);
  background: var(--glass-bg-readable);
  backdrop-filter: blur(var(--glass-blur-soft)) saturate(1.04);
  box-shadow: var(--glass-shadow-soft), inset 0 1px 0 rgb(255 255 255 / 0.68);
  padding: var(--space-5);
}

.quiz-option {
  width: 100%;
  min-height: 3rem;
  border: 1px solid var(--quiz-option-border);
  border-radius: var(--radius-panel);
  background: var(--quiz-option-bg);
  color: var(--quiz-option-color);
  cursor: pointer;
  font-family: var(--font-prose);
  font-size: var(--text-sm);
  line-height: var(--leading-ui);
  padding: var(--space-3) var(--space-4);
  text-align: left;
  transition:
    transform var(--motion-glass),
    border-color var(--motion-glass),
    box-shadow var(--motion-glass),
    background var(--motion-glass);
}

.quiz-option:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: rgb(14 165 233 / 0.38);
  box-shadow: var(--glow-cyan);
}

.quiz-option[data-correct="true"] {
  box-shadow: 0 0 0 1px rgb(22 163 74 / 0.18), 0 14px 34px rgb(22 163 74 / 0.12);
}

.quiz-option[data-wrong="true"] {
  box-shadow: 0 0 0 1px rgb(220 38 38 / 0.18), 0 14px 34px rgb(220 38 38 / 0.1);
}
```

- [ ] **Step 3: Replace inline hover handlers**

Remove `onMouseEnter` and `onMouseLeave` from quiz option buttons and submit/navigation buttons. CSS hover states now own visual behavior. Keep click and disabled behavior unchanged.

- [ ] **Step 4: Run quiz tests**

Run:

```powershell
cd D:\ai-agent\frontend
npm test -- --run src/__tests__/components/QuizCard.test.tsx
```

Expected: quiz tests pass. If tests assert inline style behavior, update them to assert state and icons instead.

- [ ] **Step 5: Commit quiz glass focus UI**

Run:

```powershell
git add frontend/src/app/globals.css frontend/src/components/QuizCard.tsx frontend/src/__tests__/components/QuizCard.test.tsx
git commit -m "style: add focused glass quiz mode"
```

Expected: commit contains only quiz-related visual changes.

## Task 6: Review Mode Glass Data Workspace

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/components/review/ReviewSummaryBar.tsx`
- Modify: `frontend/src/components/review/ReviewFilters.tsx`
- Modify: `frontend/src/components/review/WeakConceptList.tsx`
- Modify: `frontend/src/components/review/MistakeList.tsx`
- Modify: `frontend/src/components/review/MistakeDetailPanel.tsx`
- Modify: `frontend/src/components/review/ReviewExportPanel.tsx`
- Modify: `frontend/src/components/review/DailyReviewFlow.tsx`
- Modify: `frontend/src/components/review/StudyPlanDialog.tsx`
- Test: `frontend/src/__tests__/components/ReviewWorkbench.test.tsx`
- Test: `frontend/src/__tests__/components/StudyPlanDialog.test.tsx`

- [ ] **Step 1: Standardize review panel hooks**

Keep existing `.review-panel` and `.review-item` hooks. Add more specific hooks:

```tsx
<section className="review-summary-panel" aria-label="错题复习总览">
```

```tsx
<section className="review-panel review-filter-panel space-y-4" aria-label="错题筛选">
```

```tsx
<article
  key={mistake.id}
  className="review-item mistake-list-item cursor-pointer p-4 transition-colors"
  data-selected={selected}
  onClick={() => onSelect(mistake)}
>
```

```tsx
<aside className="review-panel mistake-detail-panel space-y-4 p-4" aria-label="错题详情">
```

- [ ] **Step 2: Add review workspace CSS**

Add:

```css
.review-workbench {
  background:
    radial-gradient(circle at 88% 8%, rgb(139 92 246 / 0.14), transparent 24rem),
    linear-gradient(180deg, rgb(255 255 255 / 0.28), transparent);
}

.review-summary-panel,
.review-panel {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-panel);
  background: var(--glass-bg-readable);
  backdrop-filter: blur(var(--glass-blur-soft)) saturate(1.04);
  box-shadow: var(--glass-shadow-soft), inset 0 1px 0 rgb(255 255 255 / 0.68);
}

.review-summary-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}

.review-filter-panel input,
.review-filter-panel select,
.mistake-detail-panel textarea {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-control);
  background: rgb(255 255 255 / 0.64);
}

.mistake-list-item[data-selected="true"] {
  border-color: rgb(37 99 235 / 0.34) !important;
  background: linear-gradient(135deg, rgb(219 234 254 / 0.72), rgb(207 250 254 / 0.44)) !important;
  box-shadow: var(--glow-blue);
}
```

Use `!important` only where existing inline `style` props temporarily win; remove those inline props in the same task wherever practical.

- [ ] **Step 3: Align study plan dialog with z-index and scrim tokens**

In `StudyPlanDialog.tsx`, update root scrim:

```tsx
<div
  className="study-plan-dialog-scrim fixed inset-0 flex items-center justify-center px-4"
  role="dialog"
  aria-modal="true"
  aria-label="生成复习计划"
>
```

Add CSS:

```css
.study-plan-dialog-scrim {
  z-index: var(--z-scrim);
  background: rgb(15 23 42 / 0.42);
  backdrop-filter: blur(var(--glass-blur-soft));
}

.study-plan-dialog-panel {
  z-index: var(--z-dialog);
  border: 1px solid var(--glass-border-strong);
  border-radius: var(--radius-float);
  background: var(--glass-bg-strong);
  backdrop-filter: blur(var(--glass-blur-strong)) saturate(1.14);
  box-shadow: var(--glass-shadow-float), inset 0 1px 0 rgb(255 255 255 / 0.72);
}
```

- [ ] **Step 4: Run review tests**

Run:

```powershell
cd D:\ai-agent\frontend
npm test -- --run src/__tests__/components/ReviewWorkbench.test.tsx src/__tests__/components/StudyPlanDialog.test.tsx
```

Expected: tests pass. If snapshots or style-sensitive assertions fail, update them to assert behavior, accessible labels, and visible text.

- [ ] **Step 5: Commit review glass workspace**

Run:

```powershell
git add frontend/src/app/globals.css frontend/src/components/review/ReviewSummaryBar.tsx frontend/src/components/review/ReviewFilters.tsx frontend/src/components/review/WeakConceptList.tsx frontend/src/components/review/MistakeList.tsx frontend/src/components/review/MistakeDetailPanel.tsx frontend/src/components/review/ReviewExportPanel.tsx frontend/src/components/review/DailyReviewFlow.tsx frontend/src/components/review/StudyPlanDialog.tsx frontend/src/__tests__/components/ReviewWorkbench.test.tsx frontend/src/__tests__/components/StudyPlanDialog.test.tsx
git commit -m "style: add glass review workspace"
```

Expected: commit contains review workspace and dialog visual changes.

## Task 7: Motion, Reduced Motion, Mobile, And Performance Pass

**Files:**
- Modify: `frontend/src/app/globals.css`

- [ ] **Step 1: Add spatial motion keyframes**

Add:

```css
@keyframes glass-float-in {
  from {
    opacity: 0;
    transform: translateY(10px) scale(0.985);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes aurora-drift {
  0%,
  100% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  50% {
    transform: translate3d(1.5%, -1%, 0) scale(1.02);
  }
}
```

Apply only to first-screen glass surfaces:

```css
.quick-card,
.message-bubble,
.quiz-question-card,
.review-panel,
.review-summary-panel {
  animation: glass-float-in 360ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.quick-card:nth-child(2) {
  animation-delay: 45ms;
}

.quick-card:nth-child(3) {
  animation-delay: 90ms;
}
```

- [ ] **Step 2: Strengthen reduced motion behavior**

Replace the current reduced motion block with:

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }

  .upload-spinner,
  .thinking-ring {
    animation-duration: 1.2s !important;
    animation-iteration-count: infinite !important;
  }

  .upload-spinner {
    animation-name: app-spin !important;
  }

  .thinking-ring {
    animation-name: thinking-ring !important;
  }

  .thinking-pulse,
  .thinking-step-text,
  .quick-card,
  .message-bubble,
  .quiz-question-card,
  .review-panel,
  .review-summary-panel {
    animation: none !important;
  }
}
```

- [ ] **Step 3: Lower blur and layout pressure on mobile**

Update mobile media rules:

```css
@media (max-width: 760px) {
  :root {
    --glass-blur-strong: 14px;
    --glass-blur-medium: 10px;
    --glass-blur-soft: 6px;
  }

  .app-sidebar {
    max-height: 17rem;
    border-right: 0;
    border-bottom: 1px solid var(--glass-border);
  }

  .quick-actions {
    padding-top: var(--space-6);
  }

  .quick-card,
  .chat-input-shell,
  .review-panel,
  .quiz-question-card {
    border-radius: var(--radius-panel);
  }
}
```

- [ ] **Step 4: Run formatting**

Run:

```powershell
cd D:\ai-agent\frontend
npx prettier --check src/app/globals.css
```

Expected: pass after formatting.

- [ ] **Step 5: Commit motion and mobile pass**

Run:

```powershell
git add frontend/src/app/globals.css
git commit -m "style: tune glass motion and mobile performance"
```

Expected: commit contains only motion, reduced-motion, and responsive CSS changes.

## Task 8: Final Verification And Visual QA

**Files:**
- Verify: all modified frontend files

- [ ] **Step 1: Run focused component tests**

Run:

```powershell
cd D:\ai-agent\frontend
npm test -- --run src/__tests__/components/Header.test.tsx src/__tests__/components/AppSidebar.test.tsx src/__tests__/components/ChatInput.test.tsx src/__tests__/components/MessageList.test.tsx src/__tests__/components/QuizCard.test.tsx src/__tests__/components/ReviewWorkbench.test.tsx src/__tests__/components/StudyPlanDialog.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 2: Run local formatting check for touched files**

Run:

```powershell
cd D:\ai-agent\frontend
npx prettier --check src/app/globals.css src/components/MessageList.tsx src/components/QuizCard.tsx src/components/review/ReviewSummaryBar.tsx src/components/review/ReviewFilters.tsx src/components/review/WeakConceptList.tsx src/components/review/MistakeList.tsx src/components/review/MistakeDetailPanel.tsx src/components/review/ReviewExportPanel.tsx src/components/review/DailyReviewFlow.tsx src/components/review/StudyPlanDialog.tsx
```

Expected: all matched files use Prettier style. If not, run the same command with `--write`.

- [ ] **Step 3: Run production build**

Run:

```powershell
cd D:\ai-agent\frontend
npm run build
```

Expected: Next.js build completes successfully.

- [ ] **Step 4: Restart frontend dev server with clean `.next` if CSS fails to load**

If visual QA shows unstyled HTML, run:

```powershell
$conn = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force; Start-Sleep -Seconds 2 }
Remove-Item -LiteralPath 'D:\ai-agent\frontend\.next' -Recurse -Force -ErrorAction SilentlyContinue
Start-Process -FilePath 'npm.cmd' -ArgumentList @('run','dev','--','--port','3000') -WorkingDirectory 'D:\ai-agent\frontend' -WindowStyle Hidden
```

Expected: `http://localhost:3000/_next/static/css/app/layout.css?...` returns `200` and contains `.app-shell`.

- [ ] **Step 5: Capture desktop and mobile screenshots with system Edge**

Run:

```powershell
cd D:\ai-agent\frontend
node -e "const { chromium } = require('@playwright/test'); (async()=>{ const browser=await chromium.launch({headless:true, channel:'msedge'}); for (const shot of [{name:'desktop-glass', width:1440, height:920},{name:'mobile-glass', width:390, height:844}]) { const page=await browser.newPage({viewport:{width:shot.width,height:shot.height}}); await page.goto('http://localhost:3000', {waitUntil:'networkidle', timeout:60000}); await page.screenshot({path:'D:/ai-agent/'+shot.name+'.png', fullPage:true}); await page.close(); } await browser.close(); })().catch(err=>{ console.error(err); process.exit(1); });"
```

Expected: screenshots are generated at `D:\ai-agent\desktop-glass.png` and `D:\ai-agent\mobile-glass.png`.

- [ ] **Step 6: Inspect screenshot checklist**

Open screenshots and verify:

- CSS is loaded and no raw HTML styling is visible.
- Background is low-saturation blue/cyan/purple aurora cloud.
- Sidebar and header are strong glass layers.
- Chat input is a clear bottom glass float and does not hide content.
- Quick action cards use large rounded glass surfaces.
- Text in chat, quiz, and review panels remains readable.
- Review page remains scan-friendly and not overly loose.
- No horizontal overflow at 390px width.
- Upload button, mode buttons, and send button have clear disabled/focus/hover states.

- [ ] **Step 7: Remove temporary screenshots**

Run:

```powershell
Remove-Item -LiteralPath 'D:\ai-agent\desktop-glass.png','D:\ai-agent\mobile-glass.png' -ErrorAction SilentlyContinue
```

Expected: screenshots are removed unless the user asks to keep them.

- [ ] **Step 8: Final commit**

If verification required any final fixes, commit them:

```powershell
git add frontend/src
git commit -m "style: polish glassmorphism verification fixes"
```

Expected: only final polish fixes are committed. If no final fixes were needed, skip this commit.

## Self-Review

Spec coverage:

- Low-saturation aurora background: Task 3.
- Medium and layered glass system: Tasks 2, 3, 4, 5, 6.
- Large Apple-like radius and pill controls: Tasks 2, 3, 4.
- Blue/cyan/purple highlight system: Tasks 2, 3, 4, 5.
- Mode-specific behavior: Tasks 4, 5, 6.
- Review density and long-list performance: Task 6.
- Strong spatial motion with reduced-motion fallback: Task 7.
- Tokenization, z-index, state system, and scope boundary: Tasks 2, 6, 7.
- Verification requirements: Task 8.

Placeholder scan:

- This plan contains no unresolved markers or unspecified implementation steps.
- Code snippets use existing file names, existing class names, or new class hooks defined in the same task.

Type consistency:

- JSX data attributes use string/boolean-compatible values already available in the components.
- Dynamic CSS variables in `QuizCard.tsx` use `React.CSSProperties`, which is already compatible with the React/TypeScript setup.

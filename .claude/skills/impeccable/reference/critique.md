### Purpose

Resolve one stable target, run two independent assessments, synthesize a design critique, persist a snapshot, and ask the user what to improve next. The chat response is the primary deliverable; the snapshot is an archive/backlog for future commands.

### Hard Invariants

- Assessment A (design review) and Assessment B (detector/browser evidence) are both required.
- Assessment A must finish before detector findings enter the parent synthesis context. Detector output is deterministic, but it still anchors judgment.
- If sub-agents are unavailable, fall back sequentially: finish and record Assessment A first, then run Assessment B, then synthesize.
- A skipped detector is a failed critique run unless `detect.mjs` is missing or crashes after a real attempt.
- Viewable targets require browser inspection when available.
- Any local server started only for critique visualization must run in the background, have a recorded stop method, and be stopped before final reporting unless the user asks to keep it.
- Do not claim a user-visible overlay exists unless script injection succeeded and the detector ran in the page.

### Setup

1. **Resolve the target** to a concrete file path or URL. Prefer a source path over a dev-server URL when both identify the same surface; ports drift, paths do not.
   - "the homepage" -> `site/pages/index.astro` or `index.html`
   - "the settings modal" -> the primary component file
   - "this page" -> the current URL or source file
2. **Compute the slug**:
   ```bash
   node .claude/skills/impeccable/scripts/critique-storage.mjs slug "<resolved-path-or-url>"
   ```
   Keep it. If the command exits non-zero, skip persistence and trend for this run, but continue the critique.
3. **Read `.impeccable/critique/ignore.md`** if it exists. Drop matching findings silently; it is the only prior-run input critique consumes.

### Assessment Orchestration

Delegate Assessment A and Assessment B to separate sub-agents when possible. They must not see each other's output. Do not show findings to the user until synthesis.

If browser automation is available, each assessment creates its own new tab. Never reuse an existing tab, even if it is already at the right URL.

### Assessment A: Design Review

Read relevant source files and visually inspect the live page when browser automation is available. Think like a design director.

Evaluate:
- **AI slop**: Would someone believe "AI made this" immediately? Check all DON'T guidance from the parent Impeccable skill.
- **Holistic design**: hierarchy, IA, emotional fit, discoverability, composition, typography, color, accessibility, states, copy, and edge cases.
- **Cognitive load**: consult the [Cognitive Load Assessment](#cognitive-load-assessment) section below; report checklist failures and decision points with >4 visible options.
- **Emotional journey**: peak-end rule, emotional valleys, reassurance at high-stakes moments.
- **Nielsen heuristics**: consult the [Heuristics Scoring Guide](#heuristics-scoring-guide) section below; score all 10 heuristics 0-4.

Return: AI slop verdict, heuristic scores, cognitive load, emotional journey, 2-3 strengths, 3-5 priority issues, persona red flags, minor observations, and provocative questions.

### Assessment B: Detector + Browser Evidence

Run the bundled detector and browser visualization evidence. Assessment B is mandatory and must remain isolated from Assessment A until both are complete.

CLI scan:
```bash
node .claude/skills/impeccable/scripts/detect.mjs --json [target]
```

- Pass markup files/directories as `[target]`; do not pass CSS-only files.
- For URLs, skip CLI scan and use browser visualization.
- For very large trees (500+ scannable files), narrow scope or ask.
- Exit code 0 = clean; 2 = findings.
- If the detector entrypoint is missing or fails to load, report deterministic scan unavailable and continue with browser/manual review.

Browser visualization is required for a viewable target when browser automation is available. Use a localhost dev/static URL for local files; avoid `file://` unless the available browser explicitly supports this workflow. Overlay flow:

1. Create a fresh tab and navigate.
2. Preflight mutable injection by setting `document.title` and appending a `<script>` tag. Read-only evaluate APIs do not count.
3. If mutation is unavailable, skip live server, browser presentation, and injection; report fallback signal.
4. If mutation is available, start `node .claude/skills/impeccable/scripts/live-server.mjs --background`, present the browser if supported, label `[Human]`, scroll top, inject `http://localhost:PORT/detect.js`, wait 2-3 seconds, read `impeccable` console messages, then stop the live server.
5. For multi-view targets, inject on 3-5 representative pages.

Return: CLI findings JSON/counts, browser console findings if applicable, false positives, and skipped/failed browser steps with concrete reasons.

After Assessment B returns usable CLI findings, reuse them. Do not rerun `detect.mjs` in the parent unless Assessment B failed, was truncated, or omitted count, rule names, or file locations.

### Generate Combined Critique Report

Synthesize both assessments into a single report. Do NOT simply concatenate. Weave the findings together, noting where the LLM review and detector agree, where the detector caught issues the LLM missed, and where detector findings are false positives.

The chat response is the primary user-facing deliverable. Present the full structured critique below in chat; do not replace it with a summary and a link. The persisted snapshot is only an archive/backlog for later commands.

Structure your feedback as a design director would:

#### Design Health Score
> *Consult the [Heuristics Scoring Guide](#heuristics-scoring-guide) section below.*

Present the Nielsen's 10 heuristics scores as a table:

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | ? | [specific finding or "n/a" if solid] |
| 2 | Match System / Real World | ? | |
| 3 | User Control and Freedom | ? | |
| 4 | Consistency and Standards | ? | |
| 5 | Error Prevention | ? | |
| 6 | Recognition Rather Than Recall | ? | |
| 7 | Flexibility and Efficiency | ? | |
| 8 | Aesthetic and Minimalist Design | ? | |
| 9 | Error Recovery | ? | |
| 10 | Help and Documentation | ? | |
| **Total** | | **??/40** | **[Rating band]** |

Be honest with scores. A 4 means genuinely excellent. Most real interfaces score 20-32.

#### Anti-Patterns Verdict

**Start here.** Does this look AI-generated?

**LLM assessment**: Your own evaluation of AI slop tells. Cover overall aesthetic feel, layout sameness, generic composition, missed opportunities for personality.

**Deterministic scan**: Summarize what the automated detector found, with counts and file locations. Note any additional issues the detector caught that you missed, and flag any false positives.

**Visual overlays** (if injection succeeded): Tell the user that overlays are now visible in the **[Human]** tab in their browser, highlighting the detected issues. Summarize what the console output reported. If browser visualization was attempted but injection failed, say that no reliable user-visible overlay is available and report the fallback signal instead.

#### Overall Impression
A brief gut reaction: what works, what doesn't, and the single biggest opportunity.

#### What's Working
Highlight 2-3 things done well. Be specific about why they work.

#### Priority Issues
The 3-5 most impactful design problems, ordered by importance.

For each issue, tag with **P0-P3 severity** (see [Issue Severity below](#issue-severity-p0p3) for definitions):
- **[P?] What**: Name the problem clearly
- **Why it matters**: How this hurts users or undermines goals
- **Fix**: What to do about it (be concrete)
- **Suggested command**: Which command could address this (from: /impeccable adapt, /impeccable animate, /impeccable audit, /impeccable bolder, /impeccable clarify, /impeccable colorize, /impeccable critique, /impeccable delight, /impeccable distill, /impeccable document, /impeccable harden, /impeccable layout, /impeccable onboard, /impeccable optimize, /impeccable overdrive, /impeccable polish, /impeccable quieter, /impeccable shape, /impeccable typeset)

#### Persona Red Flags
> *Consult the [Personas reference](#persona-based-design-testing) below.*

Auto-select 2-3 personas most relevant to this interface type (use the selection table in the reference). If `CLAUDE.md` contains a `## Design Context` section from `impeccable init`, also generate 1-2 project-specific personas from the audience/brand info.

For each selected persona, walk through the primary user action and list specific red flags found:

**Alex (Power User)**: No keyboard shortcuts detected. Form requires 8 clicks for primary action. Forced modal onboarding. High abandonment risk.

**Jordan (First-Timer)**: Icon-only nav in sidebar. Technical jargon in error messages ("404 Not Found"). No visible help. Will abandon at step 2.

Be specific. Name the exact elements and interactions that fail each persona. Don't write generic persona descriptions; write what broke for them.

#### Minor Observations
Quick notes on smaller issues worth addressing.

#### Questions to Consider
Provocative questions that might unlock better solutions:
- "What if the primary action were more prominent?"
- "Does this need to feel this complex?"
- "What would a confident version of this look like?"

**Remember**:
- Be direct. Vague feedback wastes everyone's time.
- Be specific. "The submit button," not "some elements."
- Say what's wrong AND why it matters to users.
- Give concrete suggestions. Cut "consider exploring..." entirely.
- Prioritize ruthlessly. If everything is important, nothing is.
- Don't soften criticism. Developers need honest feedback to ship great design.

### Persist the Snapshot

Once the report above is finalized, write it to `.impeccable/critique/` so the user can refer back, and so `/impeccable polish` can pick up the priority issues without a copy-paste.

Skip this step if the Setup slug was null (vague or root-level target).

1. **Write the body to a temp file** so you can pipe it to the helper. Use the full critique report (heuristic table, anti-patterns verdict, priority issues, persona red flags, minor observations, and questions), but stop before the "Ask the User" / "Recommended Actions" sections that come later.

2. **Pass the structured metadata** through `IMPECCABLE_CRITIQUE_META` (JSON), then run the write command:
   ```bash
   IMPECCABLE_CRITIQUE_META='{"target":"<user phrasing>","total_score":<n>,"p0_count":<n>,"p1_count":<n>}' \
     node .claude/skills/impeccable/scripts/critique-storage.mjs write <slug> <body-file>
   ```
   The helper prints the absolute path it wrote.

3. **Delete the temp body file** after the write attempt completes, whether the write succeeded or failed. If deletion fails, mention `temp-file cleanup failed: <reason>` briefly in the final output, but do not block the critique.

4. **Read the trend** for context:
   ```bash
   node .claude/skills/impeccable/scripts/critique-storage.mjs trend <slug> 5
   ```
   This returns a JSON array of the last 5 frontmatter entries (including the one you just wrote).

5. **Append a single line to the user-visible output**, after the report and before the questions:

   > **Trend for `<slug>` (last 5 runs): 24 → 28 → 32 → 29 → 32**
   > Wrote `.impeccable/critique/<filename>`.

   If this is the first run for the slug, the trend is just one score; say so: "First run for this target, no trend yet."

This is fire-and-forget. Do not show the user the helper's JSON output; only the human-readable trend line and the written path. Failures here should not block the rest of the flow; print the error and move on.

### Ask the User

**After presenting findings**, use targeted questions based on what was actually found. STOP and call the AskUserQuestion tool to clarify. These answers will shape the action plan.

Ask questions along these lines (adapt to the specific findings; do NOT ask generic questions):

1. **Priority direction**: Based on the issues found, ask which category matters most to the user right now. For example: "I found problems with visual hierarchy, color usage, and information overload. Which area should we tackle first?" Offer the top 2-3 issue categories as options.

2. **Design intent**: If the critique found a tonal mismatch, ask whether it was intentional. For example: "The interface feels clinical and corporate. Is that the intended tone, or should it feel warmer/bolder/more playful?" Offer 2-3 tonal directions as options based on what would fix the issues found.

3. **Scope**: Ask how much the user wants to take on. For example: "I found N issues. Want to address everything, or focus on the top 3?" Offer scope options like "Top 3 only", "All issues", "Critical issues only".

4. **Constraints** (optional; only ask if relevant): If the findings touch many areas, ask if anything is off-limits. For example: "Should any sections stay as-is?" This prevents the plan from touching things the user considers done.

**Rules for questions**:
- Every question must reference specific findings from the report. Never ask generic "who is your audience?" questions.
- Keep it to 2-4 questions maximum. Respect the user's time.
- Offer concrete options, not open-ended prompts.
- If findings are straightforward (e.g., only 1-2 clear issues), skip questions and go directly to Recommended Actions.

### Recommended Actions

**After receiving the user's answers**, present a prioritized action summary reflecting the user's priorities and scope from Ask the User.

#### Action Summary

List recommended commands in priority order, based on the user's answers:

1. **`/command-name`**: Brief description of what to fix (specific context from critique findings)
2. **`/command-name`**: Brief description (specific context)
...

**Rules for recommendations**:
- Only recommend commands from: /impeccable adapt, /impeccable animate, /impeccable audit, /impeccable bolder, /impeccable clarify, /impeccable colorize, /impeccable critique, /impeccable delight, /impeccable distill, /impeccable document, /impeccable harden, /impeccable layout, /impeccable onboard, /impeccable optimize, /impeccable overdrive, /impeccable polish, /impeccable quieter, /impeccable shape, /impeccable typeset
- Order by the user's stated priorities first, then by impact
- Each item's description should carry enough context that the command knows what to focus on
- Map each Priority Issue to the appropriate command
- Skip commands that would address zero issues
- If the user chose a limited scope, only include items within that scope
- If the user marked areas as off-limits, exclude commands that would touch those areas
- End with `/impeccable polish` as the final step if any fixes were recommended

After presenting the summary, tell the user:

> You can ask me to run these one at a time, all at once, or in any order you prefer.
>
> Re-run `/impeccable critique` after fixes to see your score improve.

---

## Reference Material

The sections below were previously separate reference files (`cognitive-load.md`, `heuristics-scoring.md`, `personas.md`). They live inline now so the critique flow has all its deep context in one place.

### Cognitive Load Assessment

Cognitive load is the total mental effort required to use an interface. Overloaded users make mistakes, get frustrated, and leave. This reference helps identify and fix cognitive overload.

---

#### Three Types of Cognitive Load

##### Intrinsic Load: The Task Itself
Complexity inherent to what the user is trying to do. You can't eliminate this, but you can structure it.

**Manage it by**:
- Breaking complex tasks into discrete steps
- Providing scaffolding (templates, defaults, examples)
- Progressive disclosure: show what's needed now, hide the rest
- Grouping related decisions together

##### Extraneous Load: Bad Design
Mental effort caused by poor design choices. **Eliminate this ruthlessly.** It's pure waste.

**Common sources**:
- Confusing navigation that requires mental mapping
- Unclear labels that force users to guess meaning
- Visual clutter competing for attention
- Inconsistent patterns that prevent learning
- Unnecessary steps between user intent and result

##### Germane Load: Learning Effort
Mental effort spent building understanding. This is *good* cognitive load; it leads to mastery.

**Support it by**:
- Progressive disclosure that reveals complexity gradually
- Consistent patterns that reward learning
- Feedback that confirms correct understanding
- Onboarding that teaches through action, not walls of text

---

#### Cognitive Load Checklist

Evaluate the interface against these 8 items:

- [ ] **Single focus**: Can the user complete their primary task without distraction from competing elements?
- [ ] **Chunking**: Is information presented in digestible groups (≤4 items per group)?
- [ ] **Grouping**: Are related items visually grouped together (proximity, borders, shared background)?
- [ ] **Visual hierarchy**: Is it immediately clear what's most important on the screen?
- [ ] **One thing at a time**: Can the user focus on a single decision before moving to the next?
- [ ] **Minimal choices**: Are decisions simplified (≤4 visible options at any decision point)?
- [ ] **Working memory**: Does the user need to remember information from a previous screen to act on the current one?
- [ ] **Progressive disclosure**: Is complexity revealed only when the user needs it?

**Scoring**: Count the failed items. 0–1 failures = low cognitive load (good). 2–3 = moderate (address soon). 4+ = high cognitive load (critical fix needed).

---

#### The Working Memory Rule

**Humans can hold ≤4 items in working memory at once** (Miller's Law revised by Cowan, 2001).

At any decision point, count the number of distinct options, actions, or pieces of information a user must simultaneously consider:
- **≤4 items**: Within working memory limits, manageable
- **5–7 items**: Pushing the boundary; consider grouping or progressive disclosure
- **8+ items**: Overloaded; users will skip, misclick, or abandon

**Practical applications**:
- Navigation menus: ≤5 top-level items (group the rest under clear categories)
- Form sections: ≤4 fields visible per group before a visual break
- Action buttons: 1 primary, 1–2 secondary, group the rest in a menu
- Dashboard widgets: ≤4 key metrics visible without scrolling
- Pricing tiers: ≤3 options (more causes analysis paralysis)

---

#### Common Cognitive Load Violations

##### 1. The Wall of Options
**Problem**: Presenting 10+ choices at once with no hierarchy.
**Fix**: Group into categories, highlight recommended, use progressive disclosure.

##### 2. The Memory Bridge
**Problem**: User must remember info from step 1 to complete step 3.
**Fix**: Keep relevant context visible, or repeat it where it's needed.

##### 3. The Hidden Navigation
**Problem**: User must build a mental map of where things are.
**Fix**: Always show current location (breadcrumbs, active states, progress indicators).

##### 4. The Jargon Barrier
**Problem**: Technical or domain language forces translation effort.
**Fix**: Use plain language. If domain terms are unavoidable, define them inline.

##### 5. The Visual Noise Floor
**Problem**: Every element has the same visual weight; nothing stands out.
**Fix**: Establish clear hierarchy: one primary element, 2–3 secondary, everything else muted.

##### 6. The Inconsistent Pattern
**Problem**: Similar actions work differently in different places.
**Fix**: Standardize interaction patterns. Same type of action = same type of UI.

##### 7. The Multi-Task Demand
**Problem**: Interface requires processing multiple simultaneous inputs (reading + deciding + navigating).
**Fix**: Sequence the steps. Let the user do one thing at a time.

##### 8. The Context Switch
**Problem**: User must jump between screens/tabs/modals to gather info for a single decision.
**Fix**: Co-locate the information needed for each decision. Reduce back-and-forth.

---

### Heuristics Scoring Guide

Score each of Nielsen's 10 Usability Heuristics on a 0–4 scale. Be honest: a 4 means genuinely excellent, not "good enough."

#### Nielsen's 10 Heuristics

##### 1. Visibility of System Status
Keep users informed about what's happening through timely, appropriate feedback.

##### 2. Match Between System and Real World
Speak the user's language. Follow real-world conventions.

##### 3. User Control and Freedom
Users need a clear "emergency exit" from unwanted states.

##### 4. Consistency and Standards
Users shouldn't wonder whether different words, situations, or actions mean the same thing.

##### 5. Error Prevention
Better than good error messages is a design that prevents problems in the first place.

##### 6. Recognition Rather Than Recall
Minimize memory load. Make objects, actions, and options visible or easily retrievable.

##### 7. Flexibility and Efficiency of Use
Accelerators, invisible to novices, speed up expert interaction.

##### 8. Aesthetic and Minimalist Design
Interfaces should not contain irrelevant or rarely needed information.

##### 9. Help Users Recognize, Diagnose, and Recover from Errors
Error messages should use plain language, precisely indicate the problem, and constructively suggest a solution.

##### 10. Help and Documentation
Even if the system is usable without docs, help should be easy to find, task-focused, and concise.

#### Score Summary

**Total possible**: 40 points (10 heuristics × 4 max)

| Score Range | Rating | What It Means |
|-------------|--------|---------------|
| 36–40 | Excellent | Minor polish only; ship it |
| 28–35 | Good | Address weak areas, solid foundation |
| 20–27 | Acceptable | Significant improvements needed before users are happy |
| 12–19 | Poor | Major UX overhaul required; core experience broken |
| 0–11 | Critical | Redesign needed; unusable in current state |

#### Issue Severity (P0–P3)

| Priority | Name | Description | Action |
|----------|------|-------------|--------|
| **P0** | Blocking | Prevents task completion entirely | Fix immediately |
| **P1** | Major | Causes significant difficulty or confusion | Fix before release |
| **P2** | Minor | Annoyance, but workaround exists | Fix in next pass |
| **P3** | Polish | Nice-to-fix, no real user impact | Fix if time permits |

---

### Persona-Based Design Testing

Test the interface through the eyes of 5 distinct user archetypes. Each persona exposes different failure modes that a single "design director" perspective would miss.

#### 1. Impatient Power User: "Alex"
Expert with similar products. Expects efficiency, hates hand-holding.

#### 2. Confused First-Timer: "Jordan"
Never used this type of product. Needs guidance at every step.

#### 3. Accessibility-Dependent User: "Sam"
Uses screen reader, keyboard-only navigation.

#### 4. Deliberate Stress Tester: "Riley"
Methodical user who pushes interfaces beyond the happy path.

#### 5. Distracted Mobile User: "Casey"
Using phone one-handed on the go. Frequently interrupted.

#### Selecting Personas

Choose personas based on the interface type:

| Interface Type | Primary Personas | Why |
|---------------|-----------------|-----|
| Landing page / marketing | Jordan, Riley, Casey | First impressions, trust, mobile |
| Dashboard / admin | Alex, Sam | Power users, accessibility |
| E-commerce / checkout | Casey, Riley, Jordan | Mobile, edge cases, clarity |
| Onboarding flow | Jordan, Casey | Confusion, interruption |
| Data-heavy / analytics | Alex, Sam | Efficiency, keyboard nav |
| Form-heavy / wizard | Jordan, Sam, Casey | Clarity, accessibility, mobile |
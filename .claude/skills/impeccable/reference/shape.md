Shape the UX and UI for a feature before any code is written. This command produces a **design brief**: a structured artifact that guides implementation through discovery, not guesswork.

**Scope**: Design planning only. This command does NOT write code. It produces the thinking that makes code good.

## Philosophy

Most AI-generated UIs fail not because of bad code, but because of skipped thinking. They jump to "here's a card grid" without asking "what is the user trying to accomplish?" This command inverts that: understand deeply first, so implementation is precise.

## Phase 1: Discovery Interview

**Do NOT write any code or make any design decisions during this phase.** Ask questions in conversation, 2-3 per round. STOP and call the AskUserQuestion tool to clarify.

### Interview cadence
At least one user-answer round unless PRODUCT.md/DESIGN.md already answer the inputs. Assert-then-confirm, not menu-with-escape.

### Purpose & Context: What is this for? Who uses it? What's success? User's state of mind?
### Content & Data: What content/data? Realistic ranges? Edge cases? Dynamic content? Visual assets?
### Design Direction: Color strategy, theme via scene sentence, 2-3 named anchor references
### Scope: Fidelity, breadth, interactivity, time intent
### Constraints: Technical, content, mobile/responsive, accessibility
### Anti-Goals: What should this NOT be? Biggest risk?

## Phase 1.5: Visual Direction Probe (Capability-Gated)

Generate 2-4 direction probes when: net-new/ambiguous work, mid-fi+ fidelity, native image generation available. If no image generation, announce skip in one line.

## Phase 2: Design Brief

Choose brief shape based on clarity:
- **Compact form (3-5 bullets)** when discovery was crisp
- **Full structured form** when genuinely ambiguous, multi-screen

### Brief Structure
1. Feature Summary (2-3 sentences)
2. Primary User Action
3. Design Direction (color strategy + theme sentence + anchor references)
4. Scope (fidelity, breadth, interactivity, time intent)
5. Layout Strategy
6. Key States
7. Interaction Model
8. Content Requirements
9. Recommended References
10. Open Questions

STOP and call the AskUserQuestion tool to clarify. Ask for explicit confirmation before finishing.
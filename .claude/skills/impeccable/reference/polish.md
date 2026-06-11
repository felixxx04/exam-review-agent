> **Additional context needed**: quality bar (MVP vs flagship).

Perform a meticulous final pass to catch all the small details that separate good work from great work. The difference between shipped and polished.

Detector and automated QA output are defect evidence only. A clean script result is never proof that the design is strong; gather browser evidence and inspect the real interaction path.

## Design System Discovery

Aligning the feature to the design system is **not optional**. Polish without alignment is decoration on top of drift.

1. **Find the design system**: Search for documentation, component libraries, style guides, token definitions
2. **Note the conventions**: Imports, spacing scale, color tokens, motion patterns, flow shapes
3. **Identify drift, then name the root cause**: Missing token, one-off implementation, or conceptual misalignment

## Pre-Polish Assessment

1. **Review completeness**: Functionally complete? Known issues? Quality bar? Ship timeline?
2. **Think experience-first**: Who uses this, what's the best possible experience?
3. **Identify polish areas**: Visual inconsistencies, spacing, interaction states, copy, edge cases
4. **Pull in prior critique** (optional)
5. **Triage cosmetic vs functional**

## Polish Systematically

### Visual Alignment & Spacing: Pixel-perfect, consistent spacing, optical alignment
### Information Architecture & Flow: Match shape of experience to system
### Typography Refinement: Hierarchy, line length, widows/orphans, font loading
### Color & Contrast: WCAG standards, consistent token usage, theme consistency
### Interaction States: Default, hover, focus, active, disabled, loading, error, success
### Micro-interactions & Transitions: Smooth, consistent easing, no jank, reduced motion
### Content & Copy: Consistent terminology, capitalization, grammar
### Icons & Images: Consistent style, proper alignment, alt text
### Forms & Inputs: Labels, required indicators, error messages, tab order
### Edge Cases & Error States: Loading, empty, error, success, long content, offline
### Responsiveness: All breakpoints, touch targets, readable text, no horizontal scroll
### Performance: Fast load, no layout shift, smooth interactions, optimized images
### Code Quality: No console logs, commented code, unused imports, proper ARIA

**NEVER**:
- Polish before it's functionally complete
- Polish without aligning to the design system
- Guess at design system principles instead of asking
- Introduce bugs while polishing
- Ignore systematic issues
- Perfect one thing while leaving others rough
- Create new one-off components when design system equivalents exist
- Hard-code values that should use design tokens

## Final Verification

- Use it yourself, test on real devices, ask someone else to review
- Compare to design, check all states
- Run detector/QA but never cite clean result as proof

## Clean Up

Replace custom implementations with shared versions, remove orphaned code, consolidate tokens, verify DRYness.
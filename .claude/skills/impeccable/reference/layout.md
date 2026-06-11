Space is the most underused design tool. Find the layout's actual problem (monotone spacing, weak hierarchy, identical card grids) and fix the structure, not the surface.

---

## Register

Brand: asymmetric compositions, fluid spacing with `clamp()`, intentional grid-breaking for emphasis. Rhythm through contrast: tight groupings paired with generous separations.

Product: predictable grids, consistent densities, familiar navigation patterns. Responsive behavior is structural (collapse sidebar, responsive table), not fluid typography. Consistency IS an affordance.

---

## Assess Current Layout

Analyze what's weak about the current spatial design:

1. **Spacing**: Consistent or arbitrary? All the same? Grouped tightly with generous space between groups?
2. **Visual hierarchy**: Squint test - can you identify most important element?
3. **Grid & structure**: Clear underlying structure or random? Identical card grids everywhere?
4. **Rhythm & variety**: Visual rhythm or monotonous repetition?
5. **Density**: Too cramped, too sparse, or matching content type?

**CRITICAL**: Layout problems are often the root cause of interfaces feeling "off" even when colors and fonts are fine. Space is a design material; use it with intention.

## Plan Layout Improvements

- **Spacing system**: Use a consistent scale (4pt base: 4, 8, 12, 16, 24, 32, 48, 64, 96px)
- **Hierarchy strategy**: How will space communicate importance?
- **Layout approach**: Flex for 1D, Grid for 2D, named areas for complex layouts
- **Rhythm**: Where should spacing be tight vs generous?

## Improve Layout Systematically

### Establish a Spacing System
- Use consistent spacing scale, prefer 4pt base over 8pt
- Name tokens semantically: `--space-xs` through `--space-xl`
- Use `gap` for sibling spacing instead of margins
- Apply `clamp()` for fluid spacing

### Create Visual Rhythm
- Tight grouping for related elements (8-12px)
- Generous separation between sections (48-96px)
- Varied spacing within sections

### Choose the Right Layout Tool
- **Flexbox for 1D layouts**: Rows, nav bars, button groups
- **Grid for 2D layouts**: Page structure, dashboards, data-dense interfaces
- Use named grid areas for complex page layouts
- Use **container queries** for components, viewport queries for page layouts

### Break Card Grid Monotony
- Don't default to card grids; spacing and alignment create visual grouping
- Use cards only when content is truly distinct and actionable
- Never nest cards inside cards
- Vary card sizes or mix cards with non-card content

### Strengthen Visual Hierarchy
- Use the fewest dimensions needed for clear hierarchy
- The best hierarchy combines 2-3 dimensions at once
- Be aware of reading flow: top-left to bottom-right in LTR
- Create clear content groupings through proximity and separation

### Manage Depth & Elevation
- Build a consistent shadow scale (sm → md → lg → xl)
- Use elevation to reinforce hierarchy, not as decoration

### Optical Adjustments
- Nudge visually off-center elements
- Text at margin-left: 0 looks slightly indented; use -0.05em
- Touch targets must be 44x44px minimum even when visual element is smaller

**NEVER**:
- Use arbitrary spacing values outside your scale
- Make all spacing equal (variety creates hierarchy)
- Wrap everything in cards
- Nest cards inside cards
- Use identical card grids everywhere
- Default to the hero metric layout as a template

## Verify Layout Improvements

- **Squint test**: Can you identify primary, secondary, and groupings?
- **Rhythm**: Satisfying beat of tight and generous spacing?
- **Hierarchy**: Most important content obvious within 2 seconds?
- **Breathing room**: Comfortable, not cramped or wasteful?
- **Consistency**: Spacing system applied uniformly?
- **Responsiveness**: Layout adapts gracefully across screen sizes?

When the rhythm and hierarchy land, hand off to `/impeccable polish` for the final pass.

## Live-mode signature params

Each variant MUST declare a `density` param. Drive all spacing tokens through `calc(var(--p-density, 1) * <base>)`.

```json
{"id":"density","kind":"range","min":0.6,"max":1.4,"step":0.05,"default":1,"label":"Density"}
```

For variants whose topology genuinely changes, use a `steps` param with `:scope[data-p-structure="X"]`.

```json
{"id":"structure","kind":"steps","default":"grid","label":"Structure","options":[
  {"value":"stacked","label":"Stacked"},
  {"value":"grid","label":"Grid"},
  {"value":"bento","label":"Bento"}
]}
```
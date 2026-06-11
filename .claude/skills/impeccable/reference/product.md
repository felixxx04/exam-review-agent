# Product register

When design SERVES the product: app UIs, admin dashboards, settings panels, data tables, tools, authenticated surfaces, anything where the user is in a task.

## The product slop test

Not "would someone say AI made this." Familiarity is often a feature here. The test is: would a user fluent in the category's best tools sit down and trust this interface, or pause at every subtly-off component?

Product UI's failure mode isn't flatness, it's strangeness without purpose: over-decorated buttons, mismatched form controls, gratuitous motion, display fonts where labels should be, invented affordances for standard tasks. The bar is earned familiarity. The tool should disappear into the task.

## Typography

- **One family is often right.** A well-tuned sans carries headings, buttons, labels, body, data.
- **Fixed rem scale, not fluid.** Clamp-sized headings don't serve product UI.
- **Tighter scale ratio.** 1.125-1.2 between steps is typical.
- **Line length still applies for prose** (65-75ch). Data and compact UI can run denser.

## Color

Product defaults to Restrained. Accent color for primary actions, current selection, and state indicators only, not decoration. State-rich semantic vocabulary. A second neutral layer for sidebars, toolbars, and panels.

## Layout

Responsive behavior is structural (collapse sidebar, responsive table, breakpoint-driven columns), not fluid typography.

## Components

Every interactive component has: default, hover, focus, active, disabled, loading, error. Don't ship with half of these. Skeleton states for loading, not spinners. Empty states that teach, not "nothing here." Consistent affordances across the surface.

## Motion

150-250 ms on most transitions. Motion conveys state, not decoration. No orchestrated page-load sequences.

## Product bans

- Decorative motion that doesn't convey state
- Inconsistent component vocabulary across screens
- Display fonts in UI labels, buttons, data
- Reinventing standard affordances for flavor
- Heavy color on inactive states
- Modal as first thought

## Product permissions

- System fonts and familiar sans defaults (Inter, SF Pro, system-ui stacks)
- Standard navigation patterns: top bar + side nav, breadcrumbs, tabs, command palettes
- Density: tables with many rows, panels with many labels
- Consistency over surprise
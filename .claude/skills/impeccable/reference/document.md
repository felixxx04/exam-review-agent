Generate a `DESIGN.md` file at the project root that captures the current visual design system, so AI agents generating new screens stay on-brand.

DESIGN.md follows the [official Google Stitch DESIGN.md format](https://stitch.withgoogle.com/docs/design-md/format/): YAML frontmatter carrying machine-readable design tokens, followed by a markdown body with exactly six sections in a fixed order. **Tokens are normative; prose provides context for how to apply them.** Sections may be omitted when not relevant, but **do not reorder them and do not rename them**.

## When to run

- The user just ran `/impeccable init` and needs the visual side documented.
- The skill noticed no `DESIGN.md` exists and nudged the user to create one.
- An existing `DESIGN.md` is stale (the design has drifted).
- Before a large redesign, to capture the current state as a reference.

If a `DESIGN.md` already exists, **do not silently overwrite it**. Show the user the existing file and STOP and call the AskUserQuestion tool to clarify.

## Two paths

- **Scan mode** (default): the project has design tokens, components, or rendered output. Extract, then confirm descriptive language.
- **Seed mode**: the project is pre-implementation. Interview for five high-level answers, write a minimal DESIGN.md marked `<!-- SEED -->`. Re-run in scan mode once there's code.

## The frontmatter: token schema

The YAML frontmatter is the machine-readable layer. Token refs use `{path.to.token}`. Colors as hex sRGB or OKLCH. Component sub-tokens limited to 8 props.

## The markdown body: six sections (exact order)

1. `## Overview`
2. `## Colors`
3. `## Typography`
4. `## Elevation`
5. `## Components`
6. `## Do's and Don'ts`

## Scan mode steps

### Step 1: Find the design assets
Search CSS custom properties, Tailwind config, CSS-in-JS theme files, design token files, component library, global stylesheet, visible rendered output.

### Step 2: Auto-extract what can be auto-extracted
Build structured draft from discovered tokens.

### Step 2b: Stage the frontmatter
Draft YAML frontmatter from auto-extracted tokens.

### Step 3: Ask the user for qualitative language
Creative North Star, Overview voice, Color character, Elevation philosophy, Component philosophy.

### Step 4: Write DESIGN.md
YAML frontmatter + markdown body using six-section spec.

### Step 4b: Write .impeccable/design.json sidecar
Carries what Stitch's schema can't hold: tonal ramps, shadow/elevation tokens, motion tokens, breakpoints, full component HTML/CSS snippets, narrative.

### Step 5: Confirm and refine
Show user, offer to revise.

## Seed mode steps

### Step 1: Confirm seed mode
### Step 2: Five questions (color strategy, typography direction, motion energy, three named references, one anti-reference)
### Step 3: Write seed DESIGN.md
### Step 4: Confirm

## Style guidelines

- Frontmatter first, prose second
- Cite PRODUCT.md anti-references by name
- Match the spec, don't invent new sections
- Descriptive > technical
- Functional > decorative
- Exact values in parens
- Use Named Rules
- Be forceful
- Concrete anti-pattern tests
- Reference PRODUCT.md
- Group colors by role
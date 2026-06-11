# Init Flow

The setup command for a project. One codebase crawl feeds everything it writes: PRODUCT.md, DESIGN.md, and `.impeccable/live/config.json`.

## Step 1: Load current state
Check what already exists. PRODUCT.md and DESIGN.md live at the project root or under `.agents/context/` or `docs/`. Never silently overwrite.

## Step 2: Explore the codebase
Scan README, package.json, existing components, brand assets, design tokens, style guides. Form a register hypothesis (brand vs product).

## Step 3: Ask strategic questions (for PRODUCT.md)
Interview for register confirmation, users/purpose, brand personality, anti-references, accessibility needs. 2-3 questions per round. At least one real user-answer round before drafting.

## Step 4: Write PRODUCT.md
Write after user confirms answers. Structure: Register, Users, Product Purpose, Brand Personality, Anti-references, Design Principles, Accessibility & Inclusion.

## Step 5: Decide on DESIGN.md
Offer `/impeccable document`. Code exists = scan mode; pre-implementation = seed mode.

## Step 6: Configure live mode (when code exists)
Write `.impeccable/live/config.json` with framework-appropriate settings. Run CSP detection. Only patch source files with user consent.

## Step 7: Recommend starting points
Summarize what was written, recommend 2-4 best commands to run next based on what the crawl surfaced.
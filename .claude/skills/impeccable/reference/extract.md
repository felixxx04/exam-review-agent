# Extract Flow

Identify reusable patterns, components, and design tokens, then extract and consolidate them into the design system for systematic reuse.

## Step 1: Discover the Design System
Find the design system, component library, or shared UI directory. Understand its structure.

## Step 2: Identify Patterns
Look for extraction opportunities: repeated components (3+ times), hard-coded values, inconsistent variations, composition patterns, type styles, animation patterns.

## Step 3: Plan Extraction
Components to extract, tokens to create, variants to support, naming conventions, migration path.

## Step 4: Extract & Enrich
Build improved, reusable versions with clear props API, accessibility, documentation.

## Step 5: Migrate
Replace existing uses with shared versions, test thoroughly, delete dead code.

## Step 6: Document
Update design system documentation, add examples and guidelines.

**NEVER**:
- Extract one-off implementations without generalization
- Create components so generic they are useless
- Extract without considering existing conventions
- Skip proper TypeScript types or prop documentation
- Create tokens for every single value
- Extract things that differ in intent
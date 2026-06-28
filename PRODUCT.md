# PRODUCT.md

## Register
Brand — design IS the product. The study tool's visual identity shapes trust and engagement; a student's first impression determines whether they feel this is a serious scholarly companion or another gimmicky app.

## Users
Chinese university students preparing for final exams. Stressed, time-pressed, seeking structured review. They want trustworthy and scholarly — not gamified, not institutional, not cold.

## Product Purpose
Multi-agent exam review system: RAG Q&A against uploaded materials, auto-quiz generation with adaptive difficulty, mistake tracking with weak-point dashboards and study plans.

## Brand Personality
温润学术 (Warm Academic) — like afternoon light through bamboo blinds in a book pavilion. Cultivated, not sterile. The moss-green brand color carries warmth; the background stays clean. Knowledge feels approachable, not intimidating.

Scene sentence: A student at dusk reviewing notes under warm lamplight, the room quiet except for the rustle of paper — the tool should feel like that focused, warm, unhurried space.

## Anti-references
- Canvas/Moodle LMS — institutional, sidebar-heavy, navy-accent
- SaaS dashboard — gradient-heavy, metric-hero, card-grid
- Duolingo — gamified, colorful, playful
- AI cream aesthetic — warm beige/cream bg + muted accent (the saturated 2026 default)

## Design Principles
1. Warmth through color, not surface — moss green IS the warmth; bg is pure
2. Scholarly readability — every text surface prioritizes comfortable reading
3. Focused, not cluttered — one dominant action per viewport
4. Earned familiarity — standard affordances, no invented UI patterns
5. Chinese-first — typography, spacing, layout optimized for Chinese text

## Color Strategy
Committed — one saturated moss-green color carries 30-60% of the surface. Warm amber accent for secondary emphasis. Pure white background; warmth lives in the brand colors, not in the surface.

## Palette (OKLCH)
| Role    | OKLCH                  | Notes                                       |
|---------|------------------------|---------------------------------------------|
| bg      | oklch(1.000 0.000 0)   | Pure white. Warmth from brand color, not bg |
| surface | oklch(0.965 0.006 150) | Barely tinted toward moss hue              |
| ink     | oklch(0.18 0.018 150)  | Deep text with brand hue whisper. 7:1+ ✓    |
| primary | oklch(0.42 0.12 150)   | Cultivated moss green. White text on fill   |
| accent  | oklch(0.75 0.13 80)    | Warm golden amber. White text on fill       |
| muted   | oklch(0.50 0.010 150)  | Secondary text. 3.5:1+ ✓                   |
| success | oklch(0.65 0.18 150)   | Bright moss for positive states             |
| error   | oklch(0.50 0.20 25)    | Warm red for error states                   |

## Typography
- Primary: LXGW WenKai (霞鹜文楷) — headings, prose, reading content. Warm, scholarly, distinctly Chinese.
- UI: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif — buttons, labels, navigation.
- Scale: modular 1.25 ratio, fixed rem (not fluid clamp). Tighter steps for product density.

## Accessibility & Inclusion
- WCAG AA contrast: 7:1 body text, 3.5:1 secondary
- Chinese readability: line-height 1.8+ for prose, comfortable spacing
- Keyboard navigation for all interactive elements
- Reduced motion alternatives for all animations
- Semantic HTML with ARIA where needed

Typography carries most of the information on the page. Replace generic defaults (Inter, Roboto, system fallback at flat scale) with type that reflects the brand and scales with intentional contrast.

---

## Register

Brand: run the font selection procedure in [brand.md](brand.md). Fluid `clamp()` scale, >=1.25 ratio between steps.

Product: system fonts and familiar sans stacks are legitimate here. One well-tuned family typically carries the whole UI. Fixed `rem` scale, 1.125-1.2 ratio.

---

## Assess Current Typography

1. **Font choices**: Invisible defaults? Match brand personality? Too many families?
2. **Hierarchy**: Can you tell headings from body at a glance? Sizes too close? Weight contrasts strong enough?
3. **Sizing & scale**: Consistent type scale? Body text >= 16px? Fixed rem for apps, fluid clamp() for marketing?
4. **Readability**: Line lengths 45-75ch? Line-height appropriate? Contrast sufficient?
5. **Consistency**: Same elements styled same way? Weights consistent? Letter-spacing intentional?

## Plan Typography Improvements

- **Font selection**: Fonts need replacing? What fits the brand?
- **Type scale**: Establish a modular scale (1.25 ratio)
- **Weight strategy**: Which weights for which roles?
- **Spacing**: Line-heights, letter-spacing, margins

## Improve Typography Systematically

### Font Selection
- Choose fonts reflecting brand personality
- Pair with genuine contrast or use single family in multiple weights
- Ensure web font loading doesn't cause layout shift

### Establish Hierarchy
- **5 sizes cover most needs**: caption, secondary, body, subheading, heading
- **Consistent ratio** between levels (1.25, 1.333, or 1.5)
- **Combine dimensions**: Size + weight + color + space
- **App UIs**: Fixed rem-based type scale
- **Marketing pages**: Fluid sizing via clamp(min, preferred, max) for headings

### Fix Readability
- Set max-width on text containers using ch units (max-width: 65ch)
- Adjust line-height per context
- Increase line-height for light-on-dark text
- Body text at least 16px / 1rem

### Refine Details
- Use tabular-nums for data tables
- Apply proper letter-spacing for caps and small text
- Use semantic token names (--text-body, --text-heading)
- Set font-kerning: normal

### Weight Consistency
- Define clear roles for each weight
- Don't use more than 3-4 weights
- Load only the weights you actually use

**NEVER**:
- Use more than 2-3 font families
- Pick sizes arbitrarily
- Set body text below 16px
- Use decorative/display fonts for body text
- Disable browser zoom
- Use px for font sizes; use rem
- Default to Inter/Roboto/Open Sans when personality matters

## Verify Typography Improvements

- Hierarchy clear? Readable in long passages? Consistent? Reflects brand? Performant? Accessible?

## Live-mode signature params

Scale param controlling hierarchy ratio:
```json
{"id":"scale","kind":"range","min":0.85,"max":1.3,"step":0.05,"default":1,"label":"Scale"}
```

---

## Reference Material

### Classic Typography Principles

#### Vertical Rhythm
Line-height should be the base unit for ALL vertical spacing. If body text has line-height: 1.5 on 16px type (= 24px), spacing values should be multiples of 24px.

#### Modular Scale & Hierarchy
Use fewer sizes with more contrast. A 5-size system covers most needs:
- xs (0.75rem): Captions, legal
- sm (0.875rem): Secondary UI, metadata
- base (1rem): Body text
- lg (1.25-1.5rem): Subheadings, lead text
- xl+ (2-4rem): Headlines, hero text

Popular ratios: 1.25 (major third), 1.333 (perfect fourth), 1.5 (perfect fifth).

#### Readability & Measure
Use ch units for character-based measure (max-width: 65ch). Light text on dark backgrounds needs compensation: bump line-height by 0.05-0.1, add letter-spacing 0.01-0.02em, optionally step weight up.

#### Font Selection & Pairing
The tactical selection procedure and reflex-reject list are in [brand.md](brand.md). System fonts are underrated for apps. One well-chosen family often beats two competing typefaces.

#### Web Font Loading
Use font-display: swap for visibility. Match fallback metrics to minimize shift. Preload critical weight only. Variable fonts for 3+ weights.

#### Fluid Type
Use clamp(min, preferred, max) for headings on marketing pages. Fixed rem scales for app UIs. Bound clamp() so max <= 2.5x min.

#### OpenType Features
- font-variant-numeric: diagonal-fractions for fractions
- font-variant-caps: all-small-caps for abbreviations
- font-variant-ligatures: none for code
- font-kerning: normal

#### ALL-CAPS Tracking
Add 5-12% letter-spacing to short all-caps labels and eyebrows.

#### Accessibility
- Never disable zoom (user-scalable=no)
- Use rem/em for font sizes
- Minimum 16px body text
- Text links need 44px+ tap targets
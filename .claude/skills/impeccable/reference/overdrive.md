Start your response with:

```
──────────── ⚡ OVERDRIVE ─────────────
》》》 Entering overdrive mode...
```

Push an interface past conventional limits. This isn't just about visual effects. It's about using the full power of the browser to make any part of an interface feel extraordinary.

**EXTRA IMPORTANT FOR THIS COMMAND**: Context determines what "extraordinary" means. A particle system on a creative portfolio is impressive. The same particle system on a settings page is embarrassing. But a settings page with instant optimistic saves and animated state transitions? That's extraordinary too.

### Propose Before Building

This command has the highest potential to misfire. Do NOT jump straight into implementation. You MUST:

1. **Think through 2-3 different directions**: different techniques, levels of ambition, aesthetic approaches
2. **STOP and call the AskUserQuestion tool to clarify.** to present directions and get the user's pick
3. Only proceed with the direction the user confirms

### Iterate with Browser Automation

Technically ambitious effects almost never work on the first try. You MUST actively use browser automation to preview, visually verify, and iterate.

---

## Assess What "Extraordinary" Means Here

### For visual/marketing surfaces
Sensory wow: scroll-driven reveal, shader background, cinematic page transition, cursor-responsive generative art.

### For functional UI
Feel wow: View Transitions morphing, virtual scrolling 100k rows, streaming form validation, spring-physics drag-and-drop.

### For performance-critical UI
Invisible wow: 50k item search without flicker, non-blocking complex forms, near-real-time image processing.

### For data-heavy interfaces
Fluidity wow: GPU-accelerated rendering, animated data transitions, force-directed graph layouts.

## The Toolkit

### Make transitions feel cinematic
- **View Transitions API**: shared element morphing between states
- **`@starting-style`**: animate from display: none with CSS only
- **Spring physics**: natural motion with mass, tension, damping

### Tie animation to scroll position
- **Scroll-driven animations** (`animation-timeline: scroll()`): CSS-only parallax, progress bars, reveals

### Render beyond CSS
- **WebGL**: shader effects, particle systems (Three.js, OGL, regl)
- **WebGPU**: next-gen GPU compute (limited browser support, fall back to WebGL2)
- **Canvas 2D / OffscreenCanvas**: custom rendering, off-main-thread
- **SVG filter chains**: displacement maps, turbulence, morphology

### Make data feel alive
- **Virtual scrolling**: render only visible rows (TanStack Virtual)
- **GPU-accelerated charts**: Canvas/WebGL for large datasets
- **Animated data transitions**: morph between chart states

### Animate complex properties
- **`@property`**: register custom CSS properties with types for animation
- **Web Animations API**: JS-driven animations with CSS performance

### Push performance boundaries
- **Web Workers**: off-main-thread computation
- **OffscreenCanvas**: render in Worker thread
- **WASM**: near-native performance for heavy computation

### Interact with the device
- **Web Audio API**: spatial audio, audio-reactive visualizations
- **Device APIs**: orientation, ambient light, geolocation

## Implement with Discipline

### Progressive enhancement is non-negotiable
Every technique must degrade gracefully. Use @supports, feature detection, CSS-only fallbacks.

### Performance rules
- Target 60fps. Below 50, simplify.
- Respect prefers-reduced-motion, always.
- Lazy-initialize heavy resources.
- Pause off-screen rendering.
- Test on real mid-range devices.

**NEVER**:
- Ignore prefers-reduced-motion
- Ship effects that cause jank
- Use bleeding-edge APIs without fallback
- Add sound without explicit user opt-in
- Use technical ambition to mask weak design fundamentals
- Layer multiple competing extraordinary moments
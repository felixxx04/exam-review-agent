Performance is a feature. Identify the actual bottleneck for THIS interface, fix it, then measure. Don't optimize what isn't slow.

## Assess Performance Issues

1. **Measure current state**: Core Web Vitals, load time, bundle size, runtime performance, network
2. **Identify bottlenecks**: What's slow? What's causing it? How bad? Who's affected?

**CRITICAL**: Measure before and after. Premature optimization wastes time.

## Optimization Strategy

### Loading Performance
- **Images**: Modern formats (WebP, AVIF), proper sizing, lazy loading, responsive images, compress
- **JavaScript Bundle**: Code splitting, tree shaking, remove unused deps, lazy load, dynamic imports
- **CSS**: Remove unused, critical CSS inline, minimize, CSS containment
- **Fonts**: font-display: swap/optional, subset, preload, limit weights
- **Loading Strategy**: Critical first (async/defer), preload, prefetch, service worker, HTTP/2+

### Rendering Performance
- **Avoid Layout Thrashing**: Batch reads, then batch writes
- **Optimize Rendering**: CSS contain, minimize DOM depth, content-visibility: auto, virtual scrolling
- **Reduce Paint & Composite**: transform/opacity for animation, will-change sparingly, bound expensive effects

### Animation Performance
- GPU acceleration with transform/opacity
- Smooth 60fps (16ms per frame)
- Intersection Observer for lazy triggers
- requestAnimationFrame for JS animations

### React/Framework Optimization
- memo(), useMemo(), useCallback() for expensive components
- Virtualize long lists, code split routes

### Network Optimization
- Combine small files, SVG sprites, inline critical assets
- Pagination, GraphQL, compression, caching, CDN
- Adaptive loading, optimistic UI, progressive enhancement

## Core Web Vitals Optimization

### LCP < 2.5s: Optimize hero images, inline critical CSS, preload, CDN, SSR
### FID < 100ms / INP < 200ms: Break up long tasks, defer JS, web workers
### CLS < 0.1: Set image dimensions, aspect-ratio, reserve space, no content injection above

**NEVER**:
- Optimize without measuring (premature optimization)
- Sacrifice accessibility for performance
- Use will-change everywhere
- Lazy load above-fold content
- Forget about mobile performance

## Verify Improvements

Before/after metrics, real user monitoring, different devices, slow connections, no regressions.
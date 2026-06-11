Designs that only work with perfect data aren't production-ready. Harden the interface against the inputs, errors, languages, and network conditions that real users will throw at it.

## Assess Hardening Needs

1. **Test with extreme inputs**: Very long/short text, special characters, emoji, RTL, large numbers, many items, no data
2. **Test error scenarios**: Network failures, API errors, validation errors, permission errors, rate limiting, concurrent operations
3. **Test internationalization**: Long translations, RTL languages, character sets, date/time/number formats, currency symbols

## Hardening Dimensions

### Text Overflow & Wrapping
- Single line with ellipsis, multi-line with clamp, allow wrapping
- Flex/Grid overflow prevention with min-width: 0
- Responsive text sizing with clamp()
- Test text scaling (zoom to 200%)

### Internationalization (i18n)
- Add 30-40% space budget for translations
- Use logical properties (margin-inline-start, not margin-left)
- RTL support with dir attribute
- UTF-8 encoding everywhere
- Use Intl API for date/number formatting
- Proper pluralization with i18n library

### Error Handling
- Network errors: clear messages, retry button, offline mode
- Form validation: inline errors near fields, clear messages, preserve input
- API errors: handle each status code appropriately
- Graceful degradation: core functionality without JavaScript

### Edge Cases & Boundary Conditions
- Empty states with clear next action
- Loading states with progress indication
- Large datasets with pagination/virtual scrolling
- Concurrent operations: prevent double-submission, handle race conditions
- Permission states with clear explanation
- Browser compatibility with polyfills and fallbacks

### Input Validation & Sanitization
- Client-side and server-side validation
- Clear constraints with maxlength, pattern, required
- ARIA-described-by for hints

### Accessibility Resilience
- Keyboard navigation, focus management, skip links
- Screen reader support with ARIA, live regions
- Reduced motion support
- High contrast mode testing

### Performance Resilience
- Slow connections: progressive loading, skeleton screens, offline support
- Memory leak prevention: cleanup listeners, cancel subscriptions
- Throttling and debouncing for search/scroll

**NEVER**:
- Assume perfect input (validate everything)
- Ignore internationalization
- Leave error messages generic
- Forget offline scenarios
- Trust client-side validation alone
- Use fixed widths for text
- Assume English-length text
- Block entire interface when one component errors
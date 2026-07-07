import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("thinking indicator styles", () => {
  it("defines animated answer thinking states", () => {
    const css = readFileSync("src/app/globals.css", "utf8");

    expect(css).toContain("@keyframes thinking-ring");
    expect(css).toContain("@keyframes thinking-step");
    expect(css).toMatch(/\.answer-thinking\s*\{/);
    expect(css).toMatch(
      /\.thinking-step-text\s*\{[^}]*animation:\s*thinking-step/s,
    );
  });

  it("keeps the thinking indicator animated under reduced motion", () => {
    const css = readFileSync("src/app/globals.css", "utf8");

    expect(css).toMatch(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\*,\s*\*::before,\s*\*::after\s*\{[\s\S]*animation-duration:\s*0\.01ms\s*!important;[\s\S]*transition-duration:\s*0\.01ms\s*!important/s,
    );
    expect(css).toMatch(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.upload-spinner,\s*\.thinking-ring\s*\{[\s\S]*animation-duration:\s*1\.2s\s*!important;[\s\S]*animation-iteration-count:\s*infinite\s*!important/s,
    );
    expect(css).toMatch(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.thinking-ring\s*\{[\s\S]*animation-name:\s*thinking-ring\s*!important/s,
    );
    expect(css).toMatch(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.thinking-pulse,\s*\.thinking-step-text[\s\S]*\{[\s\S]*animation:\s*none\s*!important/s,
    );
  });
});

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
      /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.thinking-ring\s*\{[\s\S]*animation:\s*thinking-ring\s+1\.2s\s+linear\s+infinite\s*!important/s,
    );
    expect(css).toMatch(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.thinking-step-text\s*\{[\s\S]*animation:\s*thinking-step\s+1\.4s\s+ease-in-out\s+infinite\s*!important/s,
    );
  });
});

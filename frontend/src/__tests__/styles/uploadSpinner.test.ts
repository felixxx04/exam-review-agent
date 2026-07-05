import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("upload spinner styles", () => {
  it("defines a real spin animation for loader icons", () => {
    const css = readFileSync("src/app/globals.css", "utf8");

    expect(css).toContain("@keyframes app-spin");
    expect(css).toMatch(/\.animate-spin\s*\{[^}]*animation:\s*app-spin/s);
  });

  it("keeps upload progress spinners moving under reduced motion", () => {
    const css = readFileSync("src/app/globals.css", "utf8");

    expect(css).toMatch(/\.upload-spinner\s*\{[^}]*animation:\s*app-spin/s);
    expect(css).toMatch(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*\.upload-spinner\s*\{[\s\S]*animation:\s*app-spin\s+1s\s+linear\s+infinite\s*!important/s,
    );
  });
});

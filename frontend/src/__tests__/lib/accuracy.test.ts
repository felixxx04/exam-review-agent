import { describe, expect, it } from "vitest";
import { getAccuracyColor } from "@/lib/accuracy";

describe("getAccuracyColor", () => {
  it("maps accuracy thresholds to the existing semantic colors", () => {
    expect(getAccuracyColor(0.6)).toBe("var(--color-success)");
    expect(getAccuracyColor(0.4)).toBe("var(--color-accent)");
    expect(getAccuracyColor(0.39)).toBe("var(--color-error)");
  });
});

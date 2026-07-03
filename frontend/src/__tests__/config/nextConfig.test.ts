import { describe, expect, it } from "vitest";
import nextConfig from "../../../next.config";

describe("nextConfig", () => {
  it("disables the Next.js dev indicator so the built-in English menu is hidden", () => {
    expect(nextConfig.devIndicators).toBe(false);
  });
});

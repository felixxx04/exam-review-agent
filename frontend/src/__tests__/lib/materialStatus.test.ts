import { describe, expect, it } from "vitest";
import {
  getMaterialStatusColor,
  getMaterialStatusIcon,
  materialStatusLabel,
} from "@/lib/materialStatus";

describe("materialStatus", () => {
  it("keeps the existing labels and colors for every material status", () => {
    expect(materialStatusLabel.ready).toBe("可使用");
    expect(materialStatusLabel.failed).toBe("处理失败");
    expect(getMaterialStatusColor("processing")).toBe("var(--color-accent)");
    expect(getMaterialStatusColor("failed")).toBe("var(--color-error)");
  });

  it("does not render a status icon for ready materials", () => {
    expect(getMaterialStatusIcon("ready")).toBeNull();
    expect(getMaterialStatusIcon("pending")).not.toBeNull();
  });
});

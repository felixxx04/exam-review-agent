import { describe, expect, it } from "vitest";
import { getNextReadyMaterialScope, sameStringList } from "@/lib/materialScope";
import type { Material } from "@/types";

const readyMaterial: Material = {
  id: 1,
  filename: "stored-mq.pdf",
  original_filename: "MQ.pdf",
  file_type: "pdf",
  file_size: 100,
  page_count: 1,
  processing_status: "ready",
  chunk_count: 1,
  error_message: null,
  created_at: new Date(0).toISOString(),
};

const redisMaterial: Material = {
  ...readyMaterial,
  id: 2,
  filename: "stored-redis.pdf",
  original_filename: "Redis.pdf",
};

const processingMaterial: Material = {
  ...readyMaterial,
  id: 3,
  filename: "stored-draft.pdf",
  original_filename: "Draft.pdf",
  processing_status: "processing",
};

describe("materialScope", () => {
  it("auto-selects the only ready material on initial load", () => {
    const result = getNextReadyMaterialScope({
      materials: [readyMaterial],
      currentScope: [],
      previousReadyNames: null,
    });

    expect(result.nextScope).toEqual(["MQ.pdf"]);
    expect([...result.readyNames]).toEqual(["MQ.pdf"]);
  });

  it("does not auto-select multiple ready materials on initial load", () => {
    const result = getNextReadyMaterialScope({
      materials: [readyMaterial, redisMaterial],
      currentScope: [],
      previousReadyNames: null,
    });

    expect(result.nextScope).toEqual([]);
  });

  it("adds newly ready materials and removes non-ready scope entries", () => {
    const result = getNextReadyMaterialScope({
      materials: [readyMaterial, redisMaterial, processingMaterial],
      currentScope: ["MQ.pdf", "Draft.pdf"],
      previousReadyNames: new Set(["MQ.pdf"]),
    });

    expect(result.nextScope).toEqual(["MQ.pdf", "Redis.pdf"]);
  });

  it("compares string lists in order", () => {
    expect(sameStringList(["a", "b"], ["a", "b"])).toBe(true);
    expect(sameStringList(["b", "a"], ["a", "b"])).toBe(false);
  });
});

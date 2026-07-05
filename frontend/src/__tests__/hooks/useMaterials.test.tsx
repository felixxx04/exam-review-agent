import { describe, expect, it, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useMaterials } from "@/hooks/useMaterials";
import { api } from "@/lib/api";
import type { Material } from "@/types";

vi.mock("@/lib/api", () => ({
  api: {
    materials: {
      list: vi.fn(),
      upload: vi.fn(),
      delete: vi.fn(),
    },
  },
}));

const material: Material = {
  id: 7,
  filename: "stored.pdf",
  original_filename: "MQ.pdf",
  file_type: "pdf",
  file_size: 128,
  page_count: 1,
  processing_status: "ready",
  chunk_count: 3,
  error_message: null,
  created_at: new Date(0).toISOString(),
};

describe("useMaterials", () => {
  beforeEach(() => {
    vi.mocked(api.materials.list).mockReset();
    vi.mocked(api.materials.upload).mockReset();
    vi.mocked(api.materials.delete).mockReset();
    vi.mocked(api.materials.list).mockResolvedValue({
      materials: [material],
      total: 1,
    });
  });

  it("loads materials through the shared api client", async () => {
    const { result } = renderHook(() => useMaterials());

    await waitFor(() => {
      expect(result.current.materials).toEqual([material]);
    });

    expect(api.materials.list).toHaveBeenCalledOnce();
  });

  it("uploads and deletes through the shared api client before refreshing", async () => {
    const file = new File(["content"], "MQ.pdf", { type: "application/pdf" });
    vi.mocked(api.materials.upload).mockResolvedValue(material);
    vi.mocked(api.materials.delete).mockResolvedValue({});

    const { result } = renderHook(() => useMaterials());
    await waitFor(() => expect(api.materials.list).toHaveBeenCalledOnce());

    await result.current.uploadMaterial(file);
    await result.current.deleteMaterial(7);

    expect(api.materials.upload).toHaveBeenCalledWith(file);
    expect(api.materials.delete).toHaveBeenCalledWith(7);
    expect(api.materials.list).toHaveBeenCalledTimes(3);
  });
});

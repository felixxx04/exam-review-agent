import { useCallback, useEffect, useState } from "react";
import type { Material } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function useMaterials() {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchMaterials = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/materials`);
      if (res.ok) {
        const body = await res.json();
        setMaterials(body.data?.materials ?? []);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const uploadMaterial = useCallback(
    async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_BASE}/api/materials`, {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        await fetchMaterials();
      }
      return res;
    },
    [fetchMaterials]
  );

  const deleteMaterial = useCallback(
    async (id: number) => {
      await fetch(`${API_BASE}/api/materials/${id}`, { method: "DELETE" });
      await fetchMaterials();
    },
    [fetchMaterials]
  );

  useEffect(() => {
    fetchMaterials();
  }, [fetchMaterials]);

  return { materials, loading, uploadMaterial, deleteMaterial, refetch: fetchMaterials };
}

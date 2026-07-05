import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Material } from "@/types";

export function useMaterials() {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchMaterials = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.materials.list();
      setMaterials(data.materials);
    } finally {
      setLoading(false);
    }
  }, []);

  const uploadMaterial = useCallback(
    async (file: File) => {
      const material = await api.materials.upload(file);
      await fetchMaterials();
      return material;
    },
    [fetchMaterials],
  );

  const deleteMaterial = useCallback(
    async (id: number) => {
      await api.materials.delete(id);
      await fetchMaterials();
    },
    [fetchMaterials],
  );

  useEffect(() => {
    fetchMaterials();
  }, [fetchMaterials]);

  return {
    materials,
    loading,
    uploadMaterial,
    deleteMaterial,
    refetch: fetchMaterials,
  };
}

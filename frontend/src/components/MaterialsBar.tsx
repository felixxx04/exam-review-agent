"use client";

import { useMaterials } from "@/hooks/useMaterials";
import { useChatStore } from "@/stores/chatStore";
import { FileText, Upload } from "lucide-react";

export function MaterialsBar() {
  const { materials, loading, uploadMaterial } = useMaterials();
  const { materialScope, setMaterialScope } = useChatStore();

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    for (const file of Array.from(files)) {
      await uploadMaterial(file);
    }
  };

  const toggleScope = (filename: string) => {
    if (materialScope.includes(filename)) {
      setMaterialScope(materialScope.filter((f) => f !== filename));
    } else {
      setMaterialScope([...materialScope, filename]);
    }
  };

  return (
    <div className="border-b border-[var(--border)] px-6 py-3 bg-[var(--bg)]">
      <div className="max-w-4xl mx-auto flex items-center gap-3">
        <label className="flex items-center gap-2 px-3 py-2 rounded-lg border border-[var(--border)] text-sm cursor-pointer hover:bg-[var(--surface)] transition-colors">
          <Upload size={16} />
          <span>上传资料</span>
          <input
            type="file"
            multiple
            accept=".pdf,.docx,.pptx"
            className="hidden"
            onChange={handleFileUpload}
          />
        </label>
        <div className="flex-1 flex gap-2 overflow-x-auto">
          {loading && <span className="text-sm text-[var(--text-secondary)]">加载中...</span>}
          {materials.map((m) => (
            <button
              key={m.id}
              onClick={() => toggleScope(m.original_filename)}
              className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
                materialScope.includes(m.original_filename)
                  ? "bg-[var(--accent)] text-white"
                  : "bg-[var(--surface)] text-[var(--text-secondary)] border border-[var(--border)]"
              }`}
            >
              <FileText size={14} />
              {m.original_filename}
              {m.processing_status === "pending" && " ..."}
              {m.processing_status === "ready" && " done"}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

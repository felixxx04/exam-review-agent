"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMaterials } from "@/hooks/useMaterials";
import { useChatStore } from "@/stores/chatStore";
import { FileText, Upload, Loader2, Check, AlertCircle, X, RotateCw } from "lucide-react";

const statusIcon: Record<string, React.ReactNode> = {
  pending: <Loader2 size={16} className="animate-spin" />,
  processing: (
    <span className="processing-icon" style={{ display: "inline-flex" }}>
      <Loader2 size={16} className="animate-spin" />
    </span>
  ),
  ready: <Check size={16} />,
  failed: <AlertCircle size={16} />,
};

const statusColor: Record<string, string> = {
  pending: "var(--color-muted)",
  processing: "var(--color-accent)",
  ready: "var(--color-success)",
  failed: "var(--color-error)",
};

export function MaterialsBar() {
  const { materials, loading, uploadMaterial, deleteMaterial, refetch } = useMaterials();
  const { materialScope, setMaterialScope } = useChatStore();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  // Auto-poll for status changes when materials are pending/processing
  useEffect(() => {
    const hasPending = materials.some(
      (m) => m.processing_status === "pending" || m.processing_status === "processing",
    );
    if (!hasPending) return;
    const id = setInterval(refetch, 3000);
    return () => clearInterval(id);
  }, [materials, refetch]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploading(true);
    // Upload files sequentially
    for (const file of Array.from(files)) {
      try {
        await uploadMaterial(file);
      } catch {
        // individual upload failure — continue with rest
      }
    }
    setUploading(false);
    if (inputRef.current) inputRef.current.value = "";
  };

  const toggleScope = (filename: string) => {
    if (materialScope.includes(filename)) {
      setMaterialScope(materialScope.filter((f) => f !== filename));
    } else {
      setMaterialScope([...materialScope, filename]);
    }
  };

  return (
    <div
      className="border-b"
      style={{
        borderColor: "var(--color-border)",
        background: "var(--color-bg)",
        padding: "var(--space-3) var(--space-5)",
      }}
    >
      <div
        className="mx-auto flex items-center gap-3"
        style={{ maxWidth: "var(--content-max)" }}
      >
        <button
          onClick={() => !uploading && inputRef.current?.click()}
          disabled={uploading}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors"
          style={{
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-border)",
            color: uploading ? "var(--color-muted)" : "var(--color-ink)",
            cursor: uploading ? "not-allowed" : "pointer",
            opacity: uploading ? 0.6 : 1,
          }}
          onMouseEnter={(e) => {
            if (!uploading) e.currentTarget.style.background = "var(--color-surface)";
          }}
          onMouseLeave={(e) => {
            if (!uploading) e.currentTarget.style.background = "transparent";
          }}
        >
          {uploading ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Upload size={16} />
          )}
          上传资料
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.pptx"
          className="hidden"
          onChange={handleFileUpload}
          aria-label="上传复习资料"
        />

        <div className="flex-1 flex gap-2 overflow-x-auto py-0.5 scrollbar-none">
          {loading && materials.length === 0 && (
            <span style={{ color: "var(--color-muted)", fontSize: "var(--text-sm)" }}>
              加载中...
            </span>
          )}
          {materials.map((m) => {
            const selected = materialScope.includes(m.original_filename);
            const isFailed = m.processing_status === "failed";
            return (
              <div
                key={m.id}
                className="flex items-center gap-0 text-sm font-medium whitespace-nowrap transition-colors"
                style={{
                  borderRadius: "var(--radius-md)",
                  background: selected
                    ? "var(--color-primary)"
                    : "var(--color-surface)",
                  border: selected
                    ? "1px solid var(--color-primary)"
                    : "1px solid var(--color-border)",
                }}
              >
                <button
                  onClick={() => toggleScope(m.original_filename)}
                  className="flex items-center gap-1.5 px-3 py-1.5"
                  style={{
                    color: selected ? "oklch(1 0 0)" : isFailed ? "var(--color-error)" : "var(--color-muted)",
                    cursor: "pointer",
                    background: "transparent",
                    border: "none",
                    fontFamily: "inherit",
                    fontSize: "inherit",
                  }}
                  onMouseEnter={(e) => {
                    if (!selected)
                      e.currentTarget.style.color = "var(--color-ink)";
                  }}
                  onMouseLeave={(e) => {
                    if (!selected)
                      e.currentTarget.style.color = isFailed ? "var(--color-error)" : "var(--color-muted)";
                  }}
                >
                  <FileText size={16} />
                  {m.original_filename}
                  {m.processing_status !== "ready" && (
                    <span
                      style={{
                        color:
                          statusColor[m.processing_status] ?? "var(--color-muted)",
                        display: "inline-flex",
                      }}
                    >
                      {statusIcon[m.processing_status]}
                    </span>
                  )}
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteMaterial(m.id);
                  }}
                  className="flex items-center justify-center p-1.5 mr-1 transition-colors"
                  style={{
                    borderRadius: "var(--radius-sm)",
                    color: selected ? "oklch(1 0 0 / 0.7)" : "var(--color-muted)",
                    cursor: "pointer",
                    background: "transparent",
                    border: "none",
                    opacity: 0.4,
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.opacity = "1";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.opacity = "0.4";
                  }}
                  aria-label={`删除 ${m.original_filename}`}
                >
                  <X size={14} />
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

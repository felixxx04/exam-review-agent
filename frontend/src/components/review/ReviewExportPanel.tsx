"use client";

import type { MistakeExportData } from "@/types";
import { Download } from "lucide-react";

interface ReviewExportPanelProps {
  exportData: MistakeExportData | null;
  exporting: boolean;
  onExport: (format: "markdown" | "csv") => void;
}

export function ReviewExportPanel({
  exportData,
  exporting,
  onExport,
}: ReviewExportPanelProps) {
  return (
    <section
      className="review-panel review-export-panel space-y-3"
      aria-label="错题导出"
    >
      <div className="flex items-center justify-between gap-2">
        <h2
          className="text-sm font-semibold"
          style={{ color: "var(--color-ink)" }}
        >
          错题导出
        </h2>
        <Download size={15} style={{ color: "var(--color-primary)" }} />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => onExport("markdown")}
          disabled={exporting}
          className="review-secondary-button review-export-button px-3 py-2 text-sm font-medium"
        >
          导出 Markdown
        </button>
        <button
          type="button"
          onClick={() => onExport("csv")}
          disabled={exporting}
          className="review-secondary-button review-export-button px-3 py-2 text-sm font-medium"
        >
          导出 CSV
        </button>
      </div>

      {exportData && (
        <pre className="review-export-preview max-h-44 overflow-auto whitespace-pre-wrap p-3 text-xs">
          {exportData.content}
        </pre>
      )}
    </section>
  );
}

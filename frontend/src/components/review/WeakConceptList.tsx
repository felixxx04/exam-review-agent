"use client";

import type { WeakConcept } from "@/types";
import { getAccuracyColor } from "@/lib/accuracy";
import { RefreshCw } from "lucide-react";

interface WeakConceptListProps {
  concepts: WeakConcept[];
  onRetest: (concept: string) => void;
}

export function WeakConceptList({ concepts, onRetest }: WeakConceptListProps) {
  return (
    <section
      className="review-panel weak-concept-panel space-y-2"
      aria-label="薄弱知识点"
    >
      <div className="flex items-center justify-between">
        <h2
          className="text-sm font-semibold"
          style={{ color: "var(--color-ink)" }}
        >
          薄弱知识点
        </h2>
        <span className="text-xs" style={{ color: "var(--color-muted)" }}>
          {concepts.length} 个
        </span>
      </div>

      {concepts.length === 0 ? (
        <p className="text-sm" style={{ color: "var(--color-muted)" }}>
          完成测验后会自动生成薄弱点。
        </p>
      ) : (
        concepts.map((concept) => (
          <div
            key={`${concept.topic}-${concept.concept}`}
            className="review-item weak-concept-card space-y-2 p-3"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p
                  className="truncate text-sm font-medium"
                  style={{ color: "var(--color-ink)" }}
                >
                  {concept.concept}
                </p>
                <p className="text-xs" style={{ color: "var(--color-muted)" }}>
                  {concept.topic || "综合"} · 错误 {concept.attempt_count} 次
                </p>
              </div>
              <span
                className="text-xs font-semibold tabular-nums"
                style={{ color: getAccuracyColor(concept.accuracy) }}
              >
                {Math.round(concept.accuracy * 100)}%
              </span>
            </div>
            <button
              type="button"
              onClick={() => onRetest(concept.concept)}
              className="review-primary-button weak-concept-retest flex w-full items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium"
            >
              <RefreshCw size={13} />
              再测 {concept.concept}
            </button>
          </div>
        ))
      )}
    </section>
  );
}

"use client";

import type { ReviewMistake } from "@/types";
import {
  formatDateTime,
  getMistakeTitle,
  REVIEW_STATUS_LABELS,
} from "@/components/review/reviewUtils";

interface MistakeListProps {
  mistakes: ReviewMistake[];
  selectedId: string | null;
  loading: boolean;
  onSelect: (mistake: ReviewMistake) => void;
  onRetestConcept: (concept: string) => void;
}

export function MistakeList({
  mistakes,
  selectedId,
  loading,
  onSelect,
  onRetestConcept,
}: MistakeListProps) {
  if (loading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((item) => (
          <div key={item} className="skeleton" style={{ height: "88px" }} />
        ))}
      </div>
    );
  }

  if (mistakes.length === 0) {
    return (
      <div className="review-panel mistake-list-empty flex min-h-64 items-center justify-center p-6 text-center">
        暂无符合条件的错题
      </div>
    );
  }

  return (
    <section className="space-y-2" aria-label="错题列表">
      {mistakes.map((mistake) => {
        const selected = mistake.id === selectedId;
        return (
          <article
            key={mistake.id}
            className="review-item mistake-list-item cursor-pointer p-4 transition-colors"
            data-selected={selected}
            onClick={() => onSelect(mistake)}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3
                  className="line-clamp-2 text-sm font-semibold"
                  style={{ color: "var(--color-ink)" }}
                >
                  {getMistakeTitle(mistake)}
                </h3>
                <p
                  className="mt-1 text-xs"
                  style={{ color: "var(--color-muted)" }}
                >
                  {mistake.topic || "综合"} · {mistake.concept} · 错误{" "}
                  {mistake.attempt_count} 次
                </p>
              </div>
              <span
                className="review-status-badge shrink-0 px-2 py-1 text-xs font-medium"
                data-selected={selected}
              >
                {REVIEW_STATUS_LABELS[mistake.status] ?? mistake.status}
              </span>
            </div>

            <div className="mt-3 flex items-center justify-between gap-3">
              <span className="text-xs" style={{ color: "var(--color-muted)" }}>
                上次错误 {formatDateTime(mistake.last_wrong_at)}
              </span>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onRetestConcept(mistake.concept);
                }}
                className="review-secondary-button mistake-list-retest px-2.5 py-1 text-xs font-medium"
              >
                再测此题知识点
              </button>
            </div>
          </article>
        );
      })}
    </section>
  );
}

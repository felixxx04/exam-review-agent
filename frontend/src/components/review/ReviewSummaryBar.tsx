"use client";

import type { ReviewSummary } from "@/types";
import { CalendarDays, RefreshCw, Target } from "lucide-react";

interface ReviewSummaryBarProps {
  summary: ReviewSummary;
  weakConceptCount: number;
  averageAccuracy: number;
  loading: boolean;
  onRefresh: () => void;
  onStartDailyReview?: () => void;
  onOpenStudyPlan?: () => void;
}

export function ReviewSummaryBar({
  summary,
  weakConceptCount,
  averageAccuracy,
  loading,
  onRefresh,
  onStartDailyReview,
  onOpenStudyPlan,
}: ReviewSummaryBarProps) {
  return (
    <section className="review-summary-panel" aria-label="错题复习总览">
      <div className="flex flex-wrap items-center gap-5 text-sm">
        <Metric label="待复习错题" value={summary.pending_count} />
        <Metric label="薄弱知识点" value={weakConceptCount} />
        <Metric
          label="平均正确率"
          value={`${Math.round(averageAccuracy * 100)}%`}
          tone="danger"
        />
        <Metric label="已掌握" value={summary.mastered_count} />
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onStartDailyReview}
          className="review-secondary-button flex items-center gap-1.5 px-3 py-2 text-sm font-medium"
        >
          <CalendarDays size={15} />
          开始今日复习
        </button>
        <button
          type="button"
          onClick={onOpenStudyPlan}
          className="review-secondary-button flex items-center gap-1.5 px-3 py-2 text-sm font-medium"
        >
          生成复习计划
        </button>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="review-primary-button flex items-center gap-1.5 px-3 py-2 text-sm font-medium"
        >
          <RefreshCw size={15} />
          刷新错题
        </button>
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  tone = "normal",
}: {
  label: string;
  value: number | string;
  tone?: "normal" | "danger";
}) {
  return (
    <div className="review-summary-metric flex items-center gap-2">
      <Target
        size={15}
        style={{
          color:
            tone === "danger" ? "var(--color-error)" : "var(--color-primary)",
        }}
      />
      <span style={{ color: "var(--color-muted)" }}>{label}</span>
      <span
        className="font-semibold tabular-nums"
        style={{
          color: tone === "danger" ? "var(--color-error)" : "var(--color-ink)",
        }}
      >
        {value}
      </span>
    </div>
  );
}

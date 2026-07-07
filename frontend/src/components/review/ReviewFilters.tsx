"use client";

import type { ReviewMistakeStatus } from "@/types";
import { REVIEW_STATUS_OPTIONS } from "@/components/review/reviewUtils";
import { Search } from "lucide-react";

interface ReviewFiltersProps {
  status: ReviewMistakeStatus | "all";
  search: string;
  sort: string;
  concepts: string[];
  concept: string;
  onStatusChange: (status: ReviewMistakeStatus | "all") => void;
  onSearchChange: (value: string) => void;
  onSortChange: (value: string) => void;
  onConceptChange: (value: string) => void;
  onClear: () => void;
}

export function ReviewFilters({
  status,
  search,
  sort,
  concepts,
  concept,
  onStatusChange,
  onSearchChange,
  onSortChange,
  onConceptChange,
  onClear,
}: ReviewFiltersProps) {
  return (
    <section
      className="review-panel review-filter-panel space-y-4"
      aria-label="错题筛选"
    >
      <div>
        <p
          className="mb-2 text-xs font-medium"
          style={{ color: "var(--color-muted)" }}
        >
          状态
        </p>
        <div className="grid grid-cols-2 gap-2">
          {REVIEW_STATUS_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onStatusChange(option.value)}
              className="review-filter-chip px-3 py-2 text-sm"
              data-selected={status === option.value}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <label className="block">
        <span
          className="mb-2 block text-xs font-medium"
          style={{ color: "var(--color-muted)" }}
        >
          搜索
        </span>
        <span className="review-filter-search flex items-center gap-2 px-3 py-2">
          <Search size={15} style={{ color: "var(--color-muted)" }} />
          <input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="题目或知识点"
            className="review-filter-input w-full bg-transparent text-sm outline-none"
          />
        </span>
      </label>

      <label className="block">
        <span
          className="mb-2 block text-xs font-medium"
          style={{ color: "var(--color-muted)" }}
        >
          知识点
        </span>
        <select
          value={concept}
          onChange={(event) => onConceptChange(event.target.value)}
          className="review-filter-input w-full px-3 py-2 text-sm"
        >
          <option value="">全部知识点</option>
          {concepts.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>

      <label className="block">
        <span
          className="mb-2 block text-xs font-medium"
          style={{ color: "var(--color-muted)" }}
        >
          排序
        </span>
        <select
          value={sort}
          onChange={(event) => onSortChange(event.target.value)}
          className="review-filter-input w-full px-3 py-2 text-sm"
        >
          <option value="priority">优先级</option>
          <option value="latest">最近错误</option>
          <option value="mistake_count">错误次数</option>
        </select>
      </label>

      <button
        type="button"
        onClick={onClear}
        className="review-secondary-button w-full px-3 py-2 text-sm font-medium"
      >
        清除筛选
      </button>
    </section>
  );
}

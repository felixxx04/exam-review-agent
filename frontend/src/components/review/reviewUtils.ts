import type { ReviewMistake, ReviewMistakeStatus, ReviewSummary } from "@/types";

export const REVIEW_STATUS_LABELS: Record<ReviewMistakeStatus, string> = {
  unreviewed: "未订正",
  corrected: "已订正",
  needs_requiz: "需再测",
  mastered: "已掌握",
};

export const REVIEW_STATUS_OPTIONS: Array<{
  value: ReviewMistakeStatus | "all";
  label: string;
}> = [
  { value: "all", label: "全部" },
  { value: "unreviewed", label: "未订正" },
  { value: "corrected", label: "已订正" },
  { value: "needs_requiz", label: "需再测" },
  { value: "mastered", label: "已掌握" },
];

export function getMistakeTitle(mistake: ReviewMistake) {
  return mistake.question_text || `${mistake.concept} 错题`;
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "暂无记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function emptySummary(): ReviewSummary {
  return {
    total_count: 0,
    pending_count: 0,
    mastered_count: 0,
    corrected_count: 0,
    needs_requiz_count: 0,
  };
}

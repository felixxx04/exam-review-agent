"use client";

import { useEffect, useState } from "react";
import type { ReviewMistake } from "@/types";
import {
  formatDateTime,
  REVIEW_STATUS_LABELS,
} from "@/components/review/reviewUtils";
import { CheckCircle2, FileText, Save, RotateCcw } from "lucide-react";

interface MistakeDetailPanelProps {
  mistake: ReviewMistake | null;
  saving: boolean;
  onSaveCorrection: (mistake: ReviewMistake, note: string) => void;
  onMarkMastered: (mistake: ReviewMistake) => void;
  onCancelMastered: (mistake: ReviewMistake) => void;
  onRetestConcept: (concept: string) => void;
}

export function MistakeDetailPanel({
  mistake,
  saving,
  onSaveCorrection,
  onMarkMastered,
  onCancelMastered,
  onRetestConcept,
}: MistakeDetailPanelProps) {
  const [note, setNote] = useState("");

  useEffect(() => {
    setNote(mistake?.correction_note ?? "");
  }, [mistake?.id, mistake?.correction_note]);

  if (!mistake) {
    return (
      <aside
        className="flex min-h-80 items-center justify-center p-6 text-center"
        style={{
          borderRadius: "var(--radius-xl)",
          border: "1px solid var(--color-border)",
          background: "var(--color-surface)",
          color: "var(--color-muted)",
        }}
      >
        选择一道错题查看详情
      </aside>
    );
  }

  return (
    <aside
      className="space-y-4 p-4"
      style={{
        borderRadius: "var(--radius-xl)",
        border: "1px solid var(--color-border)",
        background: "var(--color-surface)",
      }}
      aria-label="错题详情"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs" style={{ color: "var(--color-muted)" }}>
            {mistake.topic || "综合"} · {mistake.concept}
          </p>
          <h2 className="mt-1 text-base font-semibold" style={{ color: "var(--color-ink)" }}>
            {mistake.question_text}
          </h2>
        </div>
        <span
          className="shrink-0 px-2 py-1 text-xs font-medium"
          style={{
            borderRadius: "var(--radius-sm)",
            background: "var(--color-primary-subtle)",
            color: "var(--color-primary)",
          }}
        >
          {REVIEW_STATUS_LABELS[mistake.status] ?? mistake.status}
        </span>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <AnswerBlock label="错误答案" value={mistake.wrong_answer || "未记录"} tone="wrong" />
        <AnswerBlock label="正确答案" value={mistake.correct_answer || "未记录"} tone="correct" />
      </div>

      <section
        className="space-y-2 p-3 text-sm"
        style={{
          borderRadius: "var(--radius-lg)",
          background: "var(--color-bg)",
          border: "1px solid var(--color-border)",
        }}
      >
        <h3 className="font-medium" style={{ color: "var(--color-ink)" }}>
          解析
        </h3>
        <p style={{ color: "var(--color-muted)", lineHeight: "var(--leading-prose)" }}>
          {mistake.explanation || "暂无解析，可先写下自己的订正思路。"}
        </p>
      </section>

      <label className="block">
        <span className="mb-2 block text-sm font-medium" style={{ color: "var(--color-ink)" }}>
          订正笔记
        </span>
        <textarea
          aria-label="订正笔记"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          className="min-h-28 w-full resize-y px-3 py-2 text-sm outline-none"
          style={{
            borderRadius: "var(--radius-lg)",
            border: "1px solid var(--color-border)",
            background: "var(--color-bg)",
            color: "var(--color-ink)",
            lineHeight: "var(--leading-prose)",
          }}
          placeholder="写下这题为什么错、下次如何判断。"
        />
      </label>

      <section className="space-y-2 text-xs" style={{ color: "var(--color-muted)" }}>
        <p className="flex items-center gap-1.5">
          <FileText size={14} />
          来源：{mistake.source_material || "暂无来源信息"}
        </p>
        <p>上次错误：{formatDateTime(mistake.last_wrong_at)}</p>
        {mistake.source_chunk_ids.length > 0 && (
          <p>片段：{mistake.source_chunk_ids.join(", ")}</p>
        )}
      </section>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onSaveCorrection(mistake, note)}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium"
          style={{
            borderRadius: "var(--radius-md)",
            border: "none",
            background: "var(--color-primary)",
            color: "oklch(1 0 0)",
            opacity: saving ? 0.65 : 1,
          }}
        >
          <Save size={15} />
          保存订正
        </button>
        {mistake.status === "mastered" ? (
          <button
            type="button"
            onClick={() => onCancelMastered(mistake)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium"
            style={secondaryButtonStyle}
          >
            <RotateCcw size={15} />
            取消掌握
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onMarkMastered(mistake)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium"
            style={secondaryButtonStyle}
          >
            <CheckCircle2 size={15} />
            标记已掌握
          </button>
        )}
        <button
          type="button"
          onClick={() => onRetestConcept(mistake.concept)}
          className="px-3 py-2 text-sm font-medium"
          style={secondaryButtonStyle}
        >
          针对知识点再测
        </button>
      </div>
    </aside>
  );
}

function AnswerBlock({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "wrong" | "correct";
}) {
  return (
    <div
      className="p-3"
      style={{
        borderRadius: "var(--radius-lg)",
        border: "1px solid var(--color-border)",
        background: "var(--color-bg)",
      }}
    >
      <p
        className="mb-1 text-xs font-medium"
        style={{ color: tone === "wrong" ? "var(--color-error)" : "var(--color-success)" }}
      >
        {label}
      </p>
      <p className="text-sm" style={{ color: "var(--color-ink)" }}>
        {value}
      </p>
    </div>
  );
}

const secondaryButtonStyle = {
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-border)",
  background: "var(--color-surface)",
  color: "var(--color-ink)",
};

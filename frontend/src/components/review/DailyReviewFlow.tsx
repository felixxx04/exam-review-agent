"use client";

import { useState } from "react";
import type { ReviewMistake } from "@/types";
import { X } from "lucide-react";

interface DailyReviewFlowProps {
  mistakes: ReviewMistake[];
  onClose: () => void;
  onSaveCorrection: (mistake: ReviewMistake, note: string) => void;
  onMarkMastered: (mistake: ReviewMistake) => void;
}

export function DailyReviewFlow({
  mistakes,
  onClose,
  onSaveCorrection,
  onMarkMastered,
}: DailyReviewFlowProps) {
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [note, setNote] = useState("");
  const current = mistakes[index];

  if (!current) return null;

  const done = index >= mistakes.length - 1;

  function goNext() {
    if (done) {
      onClose();
      return;
    }
    setIndex((value) => value + 1);
    setRevealed(false);
    setNote("");
  }

  return (
    <section
      className="review-panel daily-review-panel space-y-4 p-4"
      aria-label="今日复习"
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2
            className="text-sm font-semibold"
            style={{ color: "var(--color-ink)" }}
          >
            今日复习 {index + 1} / {mistakes.length}
          </h2>
          <p className="text-xs" style={{ color: "var(--color-muted)" }}>
            {current.topic || "综合"} · {current.concept}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭今日复习"
          className="review-icon-button daily-review-close p-2"
        >
          <X size={16} />
        </button>
      </div>

      <p className="text-sm font-medium" style={{ color: "var(--color-ink)" }}>
        {current.question_text}
      </p>

      {revealed ? (
        <div
          className="daily-review-answer-grid grid gap-3 text-sm md:grid-cols-2"
          style={{ color: "var(--color-ink)" }}
        >
          <div className="daily-review-answer" data-tone="wrong">
            <p
              className="text-xs font-medium"
              style={{ color: "var(--color-error)" }}
            >
              错误答案
            </p>
            <p>{current.wrong_answer || "未记录"}</p>
          </div>
          <div className="daily-review-answer" data-tone="correct">
            <p
              className="text-xs font-medium"
              style={{ color: "var(--color-success)" }}
            >
              正确答案
            </p>
            <p>{current.correct_answer || "未记录"}</p>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setRevealed(true)}
          className="review-secondary-button daily-review-reveal px-3 py-2 text-sm font-medium"
        >
          显示答案
        </button>
      )}

      <textarea
        aria-label="今日复习订正"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="写一句今天的订正重点"
        className="daily-review-note min-h-20 w-full px-3 py-2 text-sm outline-none"
      />

      <div className="daily-review-actions flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => {
            onSaveCorrection(current, note);
            goNext();
          }}
          className="review-primary-button daily-review-action px-3 py-2 text-sm font-medium"
        >
          保存并继续
        </button>
        <button
          type="button"
          onClick={() => {
            onMarkMastered(current);
            goNext();
          }}
          className="review-secondary-button daily-review-action px-3 py-2 text-sm font-medium"
        >
          已掌握
        </button>
      </div>
    </section>
  );
}

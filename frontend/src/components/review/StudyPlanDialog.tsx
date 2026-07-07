"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { StudyPlanData } from "@/types";

interface StudyPlanDialogProps {
  open: boolean;
  loading: boolean;
  plan: StudyPlanData | null;
  onClose: () => void;
  onGenerate: (payload: {
    exam_date: string;
    days_before_exam: number;
  }) => void;
}

function defaultExamDate() {
  const date = new Date();
  date.setDate(date.getDate() + 7);
  return date.toISOString().slice(0, 10);
}

export function StudyPlanDialog({
  open,
  loading,
  plan,
  onClose,
  onGenerate,
}: StudyPlanDialogProps) {
  const [examDate, setExamDate] = useState(defaultExamDate);
  const [days, setDays] = useState(7);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!open || !mounted) return null;

  return createPortal(
    <div
      className="study-plan-dialog-scrim fixed inset-0 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-label="生成复习计划"
    >
      <section
        className="study-plan-dialog-panel w-full max-w-xl space-y-4 p-5"
        style={{
          maxHeight: "calc(100vh - 2rem)",
          overflowY: "auto",
        }}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2
              className="text-base font-semibold"
              style={{ color: "var(--color-ink)" }}
            >
              生成复习计划
            </h2>
            <p className="text-sm" style={{ color: "var(--color-muted)" }}>
              根据当前薄弱知识点安排每日复习任务。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="review-icon-button text-sm"
          >
            关闭
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label
            className="block text-sm"
            style={{ color: "var(--color-ink)" }}
          >
            考试日期
            <input
              type="date"
              value={examDate}
              onChange={(event) => setExamDate(event.target.value)}
              className="study-plan-dialog-input mt-2 w-full px-3 py-2"
            />
          </label>
          <label
            className="block text-sm"
            style={{ color: "var(--color-ink)" }}
          >
            复习天数
            <input
              type="number"
              min={1}
              max={30}
              value={days}
              onChange={(event) => setDays(Number(event.target.value))}
              className="study-plan-dialog-input mt-2 w-full px-3 py-2"
            />
          </label>
        </div>

        <button
          type="button"
          onClick={() =>
            onGenerate({ exam_date: examDate, days_before_exam: days })
          }
          disabled={loading}
          className="review-primary-button px-3 py-2 text-sm font-medium"
        >
          确认生成
        </button>

        {plan && (
          <div className="space-y-3">
            {plan.message && (
              <p className="text-sm" style={{ color: "var(--color-muted)" }}>
                {plan.message}
              </p>
            )}
            {plan.plan.map((day) => (
              <article key={day.day} className="study-plan-day-card p-3">
                <h3
                  className="text-sm font-semibold"
                  style={{ color: "var(--color-ink)" }}
                >
                  第 {day.day} 天
                </h3>
                <p
                  className="mt-1 text-xs"
                  style={{ color: "var(--color-muted)" }}
                >
                  {day.topics.join("、") || "综合复习"}
                </p>
                <ul
                  className="mt-2 space-y-1 text-sm"
                  style={{ color: "var(--color-ink)" }}
                >
                  {day.tasks.map((task) => (
                    <li key={task}>{task}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>,
    document.body,
  );
}

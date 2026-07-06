"use client";

import { useState } from "react";
import type { StudyPlanData } from "@/types";

interface StudyPlanDialogProps {
  open: boolean;
  loading: boolean;
  plan: StudyPlanData | null;
  onClose: () => void;
  onGenerate: (payload: { exam_date: string; days_before_exam: number }) => void;
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

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      style={{ background: "rgba(15, 23, 20, 0.28)" }}
      role="dialog"
      aria-modal="true"
      aria-label="生成复习计划"
    >
      <section
        className="w-full max-w-xl space-y-4 p-5"
        style={{
          borderRadius: "var(--radius-xl)",
          border: "1px solid var(--color-border)",
          background: "var(--color-surface)",
          boxShadow: "var(--shadow-lg)",
        }}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold" style={{ color: "var(--color-ink)" }}>
              生成复习计划
            </h2>
            <p className="text-sm" style={{ color: "var(--color-muted)" }}>
              根据当前薄弱知识点安排每日复习任务。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-sm"
            style={{ border: "none", background: "transparent", color: "var(--color-muted)" }}
          >
            关闭
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm" style={{ color: "var(--color-ink)" }}>
            考试日期
            <input
              type="date"
              value={examDate}
              onChange={(event) => setExamDate(event.target.value)}
              className="mt-2 w-full px-3 py-2"
              style={{
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                background: "var(--color-bg)",
              }}
            />
          </label>
          <label className="block text-sm" style={{ color: "var(--color-ink)" }}>
            复习天数
            <input
              type="number"
              min={1}
              max={30}
              value={days}
              onChange={(event) => setDays(Number(event.target.value))}
              className="mt-2 w-full px-3 py-2"
              style={{
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                background: "var(--color-bg)",
              }}
            />
          </label>
        </div>

        <button
          type="button"
          onClick={() => onGenerate({ exam_date: examDate, days_before_exam: days })}
          disabled={loading}
          className="px-3 py-2 text-sm font-medium"
          style={{
            borderRadius: "var(--radius-md)",
            border: "none",
            background: "var(--color-primary)",
            color: "oklch(1 0 0)",
            opacity: loading ? 0.65 : 1,
          }}
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
              <article
                key={day.day}
                className="p-3"
                style={{
                  borderRadius: "var(--radius-lg)",
                  border: "1px solid var(--color-border)",
                  background: "var(--color-bg)",
                }}
              >
                <h3 className="text-sm font-semibold" style={{ color: "var(--color-ink)" }}>
                  第 {day.day} 天
                </h3>
                <p className="mt-1 text-xs" style={{ color: "var(--color-muted)" }}>
                  {day.topics.join("、") || "综合复习"}
                </p>
                <ul className="mt-2 space-y-1 text-sm" style={{ color: "var(--color-ink)" }}>
                  {day.tasks.map((task) => (
                    <li key={task}>{task}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

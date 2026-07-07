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
  onSimilarQuiz: (mistake: ReviewMistake) => void;
  onExplain: (mistake: ReviewMistake) => void;
}

export function MistakeDetailPanel({
  mistake,
  saving,
  onSaveCorrection,
  onMarkMastered,
  onCancelMastered,
  onRetestConcept,
  onSimilarQuiz,
  onExplain,
}: MistakeDetailPanelProps) {
  const [note, setNote] = useState("");

  useEffect(() => {
    setNote(mistake?.correction_note ?? "");
  }, [mistake?.id, mistake?.correction_note]);

  if (!mistake) {
    return (
      <aside
        className="review-panel mistake-detail-panel mistake-detail-empty flex min-h-80 items-center justify-center p-6 text-center"
        aria-label="错题详情"
      >
        选择一道错题查看详情
      </aside>
    );
  }

  return (
    <aside
      className="review-panel mistake-detail-panel space-y-4 p-4"
      aria-label="错题详情"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs" style={{ color: "var(--color-muted)" }}>
            {mistake.topic || "综合"} · {mistake.concept}
          </p>
          <h2
            className="mt-1 text-base font-semibold"
            style={{ color: "var(--color-ink)" }}
          >
            {mistake.question_text}
          </h2>
        </div>
        <span
          className="review-status-badge shrink-0 px-2 py-1 text-xs font-medium"
          data-selected="true"
        >
          {REVIEW_STATUS_LABELS[mistake.status] ?? mistake.status}
        </span>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <AnswerBlock
          label="错误答案"
          value={mistake.wrong_answer || "未记录"}
          tone="wrong"
        />
        <AnswerBlock
          label="正确答案"
          value={mistake.correct_answer || "未记录"}
          tone="correct"
        />
      </div>

      <section className="mistake-explanation-block space-y-2 p-3 text-sm">
        <h3 className="font-medium" style={{ color: "var(--color-ink)" }}>
          解析
        </h3>
        <p
          style={{
            color: "var(--color-muted)",
            lineHeight: "var(--leading-prose)",
          }}
        >
          {mistake.explanation || "暂无解析，可先写下自己的订正思路。"}
        </p>
      </section>

      <label className="block">
        <span
          className="mb-2 block text-sm font-medium"
          style={{ color: "var(--color-ink)" }}
        >
          订正笔记
        </span>
        <textarea
          aria-label="订正笔记"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          className="mistake-detail-note min-h-28 w-full resize-y px-3 py-2 text-sm outline-none"
          placeholder="写下这题为什么错、下次如何判断。"
        />
      </label>

      <section className="mistake-meta-block space-y-2 text-xs">
        <p className="flex items-center gap-1.5">
          <FileText size={14} />
          来源：{mistake.source_material || "暂无来源信息"}
        </p>
        <p>上次错误：{formatDateTime(mistake.last_wrong_at)}</p>
        <p>下次复习：{formatDateTime(mistake.next_review_at)}</p>
        {mistake.source_chunk_ids.length > 0 && (
          <p>片段：{mistake.source_chunk_ids.join(", ")}</p>
        )}
      </section>

      <section className="mistake-history-block space-y-2 p-3 text-xs">
        <h3
          className="text-sm font-medium"
          style={{ color: "var(--color-ink)" }}
        >
          复习历史
        </h3>
        {mistake.review_history.length === 0 ? (
          <p>暂无历史记录</p>
        ) : (
          <ul className="space-y-1">
            {mistake.review_history.map((item, index) => (
              <li key={`${String(item.event)}-${index}`}>
                {String(item.event ?? "updated")} ·{" "}
                {formatDateTime(String(item.at ?? ""))}
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="mistake-detail-actions flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onSaveCorrection(mistake, note)}
          disabled={saving}
          className="review-primary-button mistake-detail-action flex items-center gap-1.5 px-3 py-2 text-sm font-medium"
        >
          <Save size={15} />
          保存订正
        </button>
        {mistake.status === "mastered" ? (
          <button
            type="button"
            onClick={() => onCancelMastered(mistake)}
            className="review-secondary-button mistake-detail-action flex items-center gap-1.5 px-3 py-2 text-sm font-medium"
          >
            <RotateCcw size={15} />
            取消掌握
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onMarkMastered(mistake)}
            className="review-secondary-button mistake-detail-action flex items-center gap-1.5 px-3 py-2 text-sm font-medium"
          >
            <CheckCircle2 size={15} />
            标记已掌握
          </button>
        )}
        <button
          type="button"
          onClick={() => onRetestConcept(mistake.concept)}
          className="review-secondary-button mistake-detail-action px-3 py-2 text-sm font-medium"
        >
          针对知识点再测
        </button>
        <button
          type="button"
          onClick={() => onSimilarQuiz(mistake)}
          className="review-secondary-button mistake-detail-action px-3 py-2 text-sm font-medium"
        >
          生成相似题
        </button>
        <button
          type="button"
          onClick={() => onExplain(mistake)}
          className="review-secondary-button mistake-detail-action px-3 py-2 text-sm font-medium"
        >
          生成错因分析
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
    <div className="mistake-answer-block p-3" data-tone={tone}>
      <p
        className="mb-1 text-xs font-medium"
        style={{
          color:
            tone === "wrong" ? "var(--color-error)" : "var(--color-success)",
        }}
      >
        {label}
      </p>
      <p className="text-sm" style={{ color: "var(--color-ink)" }}>
        {value}
      </p>
    </div>
  );
}

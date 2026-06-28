"use client";

import { useQuizStore } from "@/stores/quizStore";
import { useChatStore } from "@/stores/chatStore";
import { api } from "@/lib/api";
import { CheckCircle2, XCircle, ChevronRight, ChevronLeft, BookOpen } from "lucide-react";
import type { ScoreResult } from "@/types";

export function QuizCard() {
  const {
    questions,
    currentIndex,
    answers,
    scores,
    nextQuestion,
    prevQuestion,
    answerQuestion,
    recordScore,
  } = useQuizStore();
  const { mode } = useChatStore();

  if (mode !== "quiz") return null;

  if (questions.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center px-5">
        <div className="text-center" style={{ padding: "var(--space-5)" }}>
          <div
            className="mx-auto flex items-center justify-center"
            style={{
              width: "72px",
              height: "72px",
              borderRadius: "var(--radius-xl)",
              background: "var(--color-primary-subtle)",
              marginBottom: "var(--space-6)",
            }}
          >
            <BookOpen
              size={36}
              strokeWidth={1.2}
              style={{ color: "var(--color-primary)" }}
            />
          </div>
          <h2
            style={{
              fontFamily: "var(--font-prose)",
              fontSize: "var(--text-xl)",
              fontWeight: 600,
              color: "var(--color-ink)",
              lineHeight: "var(--leading-tight)",
              marginBottom: "var(--space-2)",
            }}
          >
            开始一次测验
          </h2>
          <p
            className="mx-auto"
            style={{
              color: "var(--color-muted)",
              fontSize: "var(--text-base)",
              lineHeight: "var(--leading-prose)",
              maxWidth: "360px",
            }}
          >
            在问答模式下输入"开始测验"来生成题目，然后检验你的掌握程度
          </p>
        </div>
      </div>
    );
  }

  const q = questions[currentIndex];
  const selected = answers[q.id];
  const score = scores[q.id];
  const isSubmitted = score !== undefined;
  const progress = ((currentIndex + 1) / questions.length) * 100;

  const handleSubmit = async () => {
    if (!selected) return;
    const result: ScoreResult = await api.quiz.submit(
      q.id,
      q.correct,
      selected,
      q.question_type
    );
    answerQuestion(q.id, selected);
    recordScore(q.id, result);
  };

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4">
      <div className="mx-auto" style={{ maxWidth: "var(--content-max)" }}>
        {/* Progress bar */}
        <div
          className="accuracy-bar mb-4"
          style={{ height: "3px" }}
        >
          <div
            className="accuracy-bar-fill"
            style={{
              width: `${progress}%`,
              background: "var(--color-primary)",
            }}
          />
        </div>

        {/* Progress text + topic tag */}
        <div
          className="mb-3 flex items-center justify-between text-xs"
          style={{ color: "var(--color-muted)" }}
        >
          <span>
            第 {currentIndex + 1} 题 / 共 {questions.length} 题
          </span>
          <span
            className="px-2 py-0.5"
            style={{
              borderRadius: "var(--radius-sm)",
              background: "var(--color-primary-subtle)",
              color: "var(--color-primary)",
              fontSize: "var(--text-xs)",
              fontWeight: 500,
            }}
          >
            {q.topic || "综合"}
          </span>
        </div>

        {/* Question card */}
        <div
          className="p-5"
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-xl)",
          }}
        >
          <p
            className="mb-5 font-medium"
            style={{
              fontFamily: "var(--font-prose)",
              fontSize: "var(--text-base)",
              lineHeight: "var(--leading-prose)",
              color: "var(--color-ink)",
            }}
          >
            {q.question}
          </p>

          {q.question_type === "multiple_choice" && q.options && (
            <div className="space-y-2">
              {q.options.map((opt, i) => {
                const letter = opt.charAt(0);
                const isSelected = selected === letter;
                const isCorrect = isSubmitted && letter === q.correct;
                const isWrong = isSubmitted && isSelected && letter !== q.correct;

                let bg = "transparent";
                let border = "var(--color-border)";
                let textColor = "var(--color-ink)";

                if (isCorrect) {
                  bg = "var(--color-success-subtle)";
                  border = "var(--color-success)";
                  textColor = "var(--color-success)";
                } else if (isWrong) {
                  bg = "var(--color-error-subtle)";
                  border = "var(--color-error)";
                  textColor = "var(--color-error)";
                } else if (isSelected) {
                  bg = "var(--color-primary-subtle)";
                  border = "var(--color-primary)";
                  textColor = "var(--color-primary)";
                }

                return (
                  <button
                    key={i}
                    onClick={() => !isSubmitted && answerQuestion(q.id, letter)}
                    disabled={isSubmitted}
                    className="w-full px-4 py-3 text-sm text-left transition-colors"
                    style={{
                      borderRadius: "var(--radius-lg)",
                      background: bg,
                      border: `1px solid ${border}`,
                      color: textColor,
                      cursor: isSubmitted ? "default" : "pointer",
                      fontFamily: "var(--font-prose)",
                      lineHeight: "var(--leading-ui)",
                    }}
                    onMouseEnter={(e) => {
                      if (!isSubmitted && !isSelected) {
                        e.currentTarget.style.background = "var(--color-surface-hover)";
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isSubmitted && !isSelected) {
                        e.currentTarget.style.background = bg;
                      }
                    }}
                  >
                    <span className="flex items-center justify-between">
                      {opt}
                      {isCorrect && <CheckCircle2 size={16} style={{ color: "var(--color-success)" }} />}
                      {isWrong && <XCircle size={16} style={{ color: "var(--color-error)" }} />}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Explanation */}
          {isSubmitted && q.explanation && (
            <div
              className="mt-4 p-4 text-sm"
              style={{
                borderRadius: "var(--radius-lg)",
                background: "var(--color-bg)",
                border: "1px solid var(--color-border)",
                fontFamily: "var(--font-prose)",
                lineHeight: "var(--leading-prose)",
              }}
            >
              <p className="font-medium mb-1" style={{ color: "var(--color-ink)" }}>
                解析
              </p>
              <p style={{ color: "var(--color-muted)" }}>{q.explanation}</p>
            </div>
          )}

          {/* Submit button */}
          {!isSubmitted && selected && (
            <button
              onClick={handleSubmit}
              className="mt-4 px-5 py-2 text-sm font-medium transition-colors"
              style={{
                borderRadius: "var(--radius-lg)",
                background: "var(--color-primary)",
                color: "oklch(1 0 0)",
                cursor: "pointer",
                border: "none",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--color-primary-hover)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "var(--color-primary)";
              }}
            >
              提交答案
            </button>
          )}
        </div>

        {/* Navigation */}
        <div
          className="mt-3 flex justify-between"
          style={{ color: "var(--color-muted)" }}
        >
          <button
            onClick={prevQuestion}
            disabled={currentIndex === 0}
            className="flex items-center gap-1 px-3 py-2 text-sm transition-colors"
            style={{
              cursor: currentIndex === 0 ? "not-allowed" : "pointer",
              opacity: currentIndex === 0 ? 0.3 : 1,
              background: "transparent",
              border: "none",
              color: "var(--color-muted)",
            }}
            onMouseEnter={(e) => {
              if (currentIndex > 0) {
                e.currentTarget.style.color = "var(--color-ink)";
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = "var(--color-muted)";
            }}
          >
            <ChevronLeft size={16} /> 上一题
          </button>
          <button
            onClick={nextQuestion}
            disabled={currentIndex === questions.length - 1}
            className="flex items-center gap-1 px-3 py-2 text-sm transition-colors"
            style={{
              cursor: currentIndex === questions.length - 1 ? "not-allowed" : "pointer",
              opacity: currentIndex === questions.length - 1 ? 0.3 : 1,
              background: "transparent",
              border: "none",
              color: "var(--color-muted)",
            }}
            onMouseEnter={(e) => {
              if (currentIndex < questions.length - 1) {
                e.currentTarget.style.color = "var(--color-ink)";
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = "var(--color-muted)";
            }}
          >
            下一题 <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

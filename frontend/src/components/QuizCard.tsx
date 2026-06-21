"use client";

import { useState } from "react";
import { useQuizStore } from "@/stores/quizStore";
import { useChatStore } from "@/stores/chatStore";
import { api } from "@/lib/api";
import { CheckCircle2, XCircle, ChevronRight, ChevronLeft } from "lucide-react";
import type { QuizQuestion, ScoreResult } from "@/types";

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

  if (mode !== "quiz" || questions.length === 0) return null;

  const q = questions[currentIndex];
  const selected = answers[q.id];
  const score = scores[q.id];
  const isSubmitted = score !== undefined;

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
    <div className="flex-1 overflow-y-auto px-6 py-4">
      <div className="max-w-4xl mx-auto">
        <div className="mb-4 flex items-center justify-between text-sm text-[var(--text-secondary)]">
          <span>题目 {currentIndex + 1} / {questions.length}</span>
          <span className="px-2 py-1 rounded bg-[var(--surface)]">
            {q.topic || "综合"}
          </span>
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-6">
          <p className="text-base font-medium mb-6">{q.question}</p>

          {q.question_type === "multiple_choice" && q.options && (
            <div className="space-y-3">
              {q.options.map((opt, i) => {
                const letter = opt.charAt(0);
                const isSelected = selected === letter;
                const isCorrect = isSubmitted && letter === q.correct;
                const isWrong = isSubmitted && isSelected && letter !== q.correct;

                return (
                  <button
                    key={i}
                    onClick={() => !isSubmitted && answerQuestion(q.id, letter)}
                    disabled={isSubmitted}
                    className={`w-full px-4 py-3 rounded-xl text-sm text-left transition-colors ${
                      isCorrect
                        ? "bg-[var(--success)]/10 border-[var(--success)] border"
                        : isWrong
                        ? "bg-[var(--error)]/10 border-[var(--error)] border"
                        : isSelected
                        ? "bg-[var(--accent)]/10 border-[var(--accent)] border"
                        : "border border-[var(--border)] hover:bg-[var(--surface)]"
                    }`}
                  >
                    {opt}
                    {isCorrect && <CheckCircle2 size={16} className="inline ml-2 text-[var(--success)]" />}
                    {isWrong && <XCircle size={16} className="inline ml-2 text-[var(--error)]" />}
                  </button>
                );
              })}
            </div>
          )}

          {isSubmitted && q.explanation && (
            <div className="mt-4 p-4 rounded-xl bg-white border border-[var(--border)] text-sm">
              <p className="font-medium mb-1">解析</p>
              <p className="text-[var(--text-secondary)]">{q.explanation}</p>
            </div>
          )}

          {!isSubmitted && selected && (
            <button
              onClick={handleSubmit}
              className="mt-4 px-6 py-2.5 rounded-xl bg-[var(--accent)] text-white text-sm font-medium hover:bg-[var(--accent-hover)]"
            >
              提交答案
            </button>
          )}
        </div>

        <div className="mt-4 flex justify-between">
          <button
            onClick={prevQuestion}
            disabled={currentIndex === 0}
            className="flex items-center gap-1 px-3 py-2 text-sm text-[var(--text-secondary)] disabled:opacity-30"
          >
            <ChevronLeft size={16} /> 上一题
          </button>
          <button
            onClick={nextQuestion}
            disabled={currentIndex === questions.length - 1}
            className="flex items-center gap-1 px-3 py-2 text-sm text-[var(--text-secondary)] disabled:opacity-30"
          >
            下一题 <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

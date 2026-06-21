"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";
import { useQuizStore } from "@/stores/quizStore";
import type { WeakConcept } from "@/types";

export function DashboardCard() {
  const { mode, setMode } = useChatStore();
  const { setGenerating } = useQuizStore();
  const [weakConcepts, setWeakConcepts] = useState<WeakConcept[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (mode === "review") {
      setLoading(true);
      api.review.weakPoints().then((data) => {
        setWeakConcepts(data.weak_concepts || []);
        setLoading(false);
      }).catch(() => setLoading(false));
    }
  }, [mode]);

  if (mode !== "review") return null;

  const startReQuiz = async (concept: string) => {
    setGenerating(true);
    setMode("quiz");
    await api.quiz.generate(concept, 0.3, 3);
    setGenerating(false);
  };

  const total = weakConcepts.length;
  const avgAccuracy =
    total > 0
      ? weakConcepts.reduce((sum, c) => sum + c.accuracy, 0) / total
      : 0;

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4">
      <div className="max-w-4xl mx-auto">
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-4 text-center">
            <p className="text-3xl font-bold">{total}</p>
            <p className="text-sm text-[var(--text-secondary)]">薄弱知识点</p>
          </div>
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-4 text-center">
            <p className="text-3xl font-bold">{Math.round(avgAccuracy * 100)}%</p>
            <p className="text-sm text-[var(--text-secondary)]">平均正确率</p>
          </div>
        </div>

        {loading && <p className="text-sm text-[var(--text-secondary)]">加载中...</p>}

        {!loading && total === 0 && (
          <div className="text-center py-8 text-[var(--text-secondary)]">
            <p className="text-lg font-medium">暂无薄弱知识点</p>
            <p className="text-sm mt-2">完成一些测验后再来查看</p>
          </div>
        )}

        {!loading && total > 0 && (
          <div className="space-y-2">
            {weakConcepts.map((c, i) => (
              <div
                key={i}
                className="flex items-center justify-between px-4 py-3 bg-[var(--surface)] border border-[var(--border)] rounded-xl"
              >
                <div>
                  <p className="text-sm font-medium">{c.concept}</p>
                  <p className="text-xs text-[var(--text-secondary)]">
                    {c.topic} · 错误 {c.attempt_count} 次
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium">
                    {Math.round(c.accuracy * 100)}%
                  </span>
                  <button
                    onClick={() => startReQuiz(c.concept)}
                    className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-white text-xs font-medium"
                  >
                    再测一次
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

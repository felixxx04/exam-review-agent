"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";
import { useQuizStore } from "@/stores/quizStore";
import type { WeakConcept } from "@/types";
import { BarChart3, RefreshCw } from "lucide-react";

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
    <div className="flex-1 overflow-y-auto px-5 py-4">
      <div className="mx-auto" style={{ maxWidth: "var(--content-max)" }}>
        {/* Inline summary — NOT hero-metric template */}
        <div
          className="flex items-center gap-6 mb-5 text-sm"
          style={{
            padding: "var(--space-3) var(--space-4)",
            borderRadius: "var(--radius-lg)",
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
          }}
        >
          <div className="flex items-center gap-2">
            <BarChart3 size={16} style={{ color: "var(--color-primary)" }} />
            <span style={{ color: "var(--color-muted)" }}>薄弱知识点</span>
            <span className="font-semibold" style={{ color: "var(--color-ink)" }}>
              {total}
            </span>
          </div>
          <div
            style={{
              width: "1px",
              height: "16px",
              background: "var(--color-border)",
            }}
          />
          <div className="flex items-center gap-2">
            <span style={{ color: "var(--color-muted)" }}>平均正确率</span>
            <span
              className="font-semibold"
              style={{
                color: avgAccuracy >= 0.6
                  ? "var(--color-success)"
                  : avgAccuracy >= 0.4
                  ? "var(--color-accent)"
                  : "var(--color-error)",
              }}
            >
              {Math.round(avgAccuracy * 100)}%
            </span>
          </div>
        </div>

        {/* Loading skeleton */}
        {loading && (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="skeleton"
                style={{ height: "52px" }}
              />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && total === 0 && (
          <div
            className="text-center"
            style={{
              padding: "var(--space-10) var(--space-5)",
            }}
          >
            <div
              className="mx-auto flex items-center justify-center"
              style={{
                width: "72px",
                height: "72px",
                borderRadius: "var(--radius-xl)",
                background: "var(--color-primary-subtle)",
                marginBottom: "var(--space-5)",
              }}
            >
              <BarChart3
                size={36}
                strokeWidth={1.2}
                style={{ color: "var(--color-primary)" }}
              />
            </div>
            <h3
              style={{
                fontFamily: "var(--font-prose)",
                fontSize: "var(--text-lg)",
                fontWeight: 600,
                color: "var(--color-ink)",
                lineHeight: "var(--leading-tight)",
                marginBottom: "var(--space-2)",
              }}
            >
              暂无薄弱知识点
            </h3>
            <p
              className="mx-auto"
              style={{
                color: "var(--color-muted)",
                fontSize: "var(--text-base)",
                lineHeight: "var(--leading-prose)",
                maxWidth: "320px",
              }}
            >
              完成一些测验后再来查看，系统会自动记录你的薄弱环节
            </p>
          </div>
        )}

        {/* Weak concepts list */}
        {!loading && total > 0 && (
          <div className="space-y-2">
            {weakConcepts.map((c, i) => (
              <div
                key={i}
                className="flex items-center justify-between px-4 py-3 transition-colors"
                style={{
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-lg)",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "var(--color-primary)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "var(--color-border)";
                }}
              >
                <div className="flex-1 min-w-0 mr-4">
                  <p
                    className="text-sm font-medium truncate"
                    style={{ color: "var(--color-ink)" }}
                  >
                    {c.concept}
                  </p>
                  <div
                    className="flex items-center gap-2 mt-1 text-xs"
                    style={{ color: "var(--color-muted)" }}
                  >
                    <span>{c.topic}</span>
                    <span>·</span>
                    <span>错误 {c.attempt_count} 次</span>
                    <div
                      className="accuracy-bar flex-1 max-w-20"
                      style={{ height: "3px" }}
                    >
                      <div
                        className="accuracy-bar-fill"
                        style={{
                          width: `${c.accuracy * 100}%`,
                          background:
                            c.accuracy >= 0.6
                              ? "var(--color-success)"
                              : c.accuracy >= 0.4
                              ? "var(--color-accent)"
                              : "var(--color-error)",
                        }}
                      />
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <span
                    className="text-sm font-medium tabular-nums"
                    style={{
                      color:
                        c.accuracy >= 0.6
                          ? "var(--color-success)"
                          : c.accuracy >= 0.4
                          ? "var(--color-accent)"
                          : "var(--color-error)",
                    }}
                  >
                    {Math.round(c.accuracy * 100)}%
                  </span>
                  <button
                    onClick={() => startReQuiz(c.concept)}
                    className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium transition-colors"
                    style={{
                      borderRadius: "var(--radius-md)",
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
                    <RefreshCw size={12} />
                    再测
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

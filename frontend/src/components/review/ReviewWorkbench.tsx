"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";
import { useQuizStore } from "@/stores/quizStore";
import type {
  MistakeListData,
  ReviewMistake,
  ReviewMistakeStatus,
  WeakConcept,
} from "@/types";
import { ReviewSummaryBar } from "@/components/review/ReviewSummaryBar";
import { ReviewFilters } from "@/components/review/ReviewFilters";
import { WeakConceptList } from "@/components/review/WeakConceptList";
import { MistakeList } from "@/components/review/MistakeList";
import { MistakeDetailPanel } from "@/components/review/MistakeDetailPanel";
import { emptySummary } from "@/components/review/reviewUtils";

export function ReviewWorkbench() {
  const { setMode } = useChatStore();
  const { setGenerating, setQuestions } = useQuizStore();
  const [mistakeData, setMistakeData] = useState<MistakeListData>({
    mistakes: [],
    total: 0,
    summary: emptySummary(),
  });
  const [weakConcepts, setWeakConcepts] = useState<WeakConcept[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [status, setStatus] = useState<ReviewMistakeStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [concept, setConcept] = useState("");
  const [sort, setSort] = useState("priority");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedMistake =
    mistakeData.mistakes.find((mistake) => mistake.id === selectedId) ??
    mistakeData.mistakes[0] ??
    null;

  const averageAccuracy = useMemo(() => {
    if (weakConcepts.length === 0) return 0;
    return (
      weakConcepts.reduce((sum, item) => sum + item.accuracy, 0) /
      weakConcepts.length
    );
  }, [weakConcepts]);

  const conceptOptions = useMemo(() => {
    return Array.from(
      new Set([
        ...weakConcepts.map((item) => item.concept),
        ...mistakeData.mistakes.map((item) => item.concept),
      ].filter(Boolean)),
    );
  }, [mistakeData.mistakes, weakConcepts]);

  async function loadReviewData() {
    setLoading(true);
    setError(null);
    try {
      const [weakPoints, mistakes] = await Promise.all([
        api.review.weakPoints(),
        api.review.mistakes({
          status: status === "all" ? undefined : status,
          concept,
          search,
          sort,
        }),
      ]);
      setWeakConcepts(weakPoints.weak_concepts || []);
      setMistakeData(mistakes);
      setSelectedId((current) => {
        if (current && mistakes.mistakes.some((item) => item.id === current)) {
          return current;
        }
        return mistakes.mistakes[0]?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "复习数据加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadReviewData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, concept, search, sort]);

  async function updateMistake(id: string, next: ReviewMistake) {
    setMistakeData((current) => ({
      ...current,
      mistakes: current.mistakes.map((item) => (item.id === id ? next : item)),
      summary: {
        ...current.summary,
        mastered_count:
          next.status === "mastered"
            ? current.summary.mastered_count + 1
            : current.summary.mastered_count,
      },
    }));
  }

  async function saveCorrection(mistake: ReviewMistake, note: string) {
    setSaving(true);
    try {
      const updated = await api.review.updateMistake(mistake.id, {
        correction_note: note,
        status: "corrected",
      });
      await updateMistake(mistake.id, updated);
    } finally {
      setSaving(false);
    }
  }

  async function markMastered(mistake: ReviewMistake) {
    setSaving(true);
    try {
      const updated = await api.review.updateMistake(mistake.id, {
        mastered: true,
      });
      await updateMistake(mistake.id, updated);
    } finally {
      setSaving(false);
    }
  }

  async function cancelMastered(mistake: ReviewMistake) {
    setSaving(true);
    try {
      const updated = await api.review.updateMistake(mistake.id, {
        mastered: false,
      });
      await updateMistake(mistake.id, updated);
    } finally {
      setSaving(false);
    }
  }

  async function retestConcept(nextConcept: string) {
    setGenerating(true);
    setMode("quiz");
    try {
      const quiz = await api.quiz.generate(nextConcept, 0.3, 3);
      setQuestions(quiz.questions, quiz.topic);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4">
      <div className="mx-auto space-y-4" style={{ maxWidth: "min(1480px, calc(100vw - 40px))" }}>
        <ReviewSummaryBar
          summary={mistakeData.summary}
          weakConceptCount={weakConcepts.length}
          averageAccuracy={averageAccuracy}
          loading={loading}
          onRefresh={loadReviewData}
          onStartDailyReview={() => undefined}
        />

        {error && (
          <div
            className="flex items-center justify-between gap-3 p-3 text-sm"
            style={{
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--color-error)",
              background: "var(--color-surface)",
              color: "var(--color-error)",
            }}
          >
            <span>{error}</span>
            <button type="button" onClick={loadReviewData} className="font-medium">
              重试
            </button>
          </div>
        )}

        <div className="grid gap-4 xl:grid-cols-[280px_minmax(360px,1fr)_420px]">
          <div className="space-y-5">
            <ReviewFilters
              status={status}
              search={search}
              sort={sort}
              concepts={conceptOptions}
              concept={concept}
              onStatusChange={setStatus}
              onSearchChange={setSearch}
              onSortChange={setSort}
              onConceptChange={setConcept}
              onClear={() => {
                setStatus("all");
                setSearch("");
                setConcept("");
                setSort("priority");
              }}
            />
            <WeakConceptList concepts={weakConcepts} onRetest={retestConcept} />
          </div>

          <MistakeList
            mistakes={mistakeData.mistakes}
            selectedId={selectedMistake?.id ?? null}
            loading={loading}
            onSelect={(mistake) => setSelectedId(mistake.id)}
            onRetestConcept={retestConcept}
          />

          <MistakeDetailPanel
            mistake={selectedMistake}
            saving={saving}
            onSaveCorrection={saveCorrection}
            onMarkMastered={markMastered}
            onCancelMastered={cancelMastered}
            onRetestConcept={retestConcept}
          />
        </div>
      </div>
    </div>
  );
}

import type { DashboardData, Material, QuizData, ScoreResult } from "@/types";

interface MaterialListData {
  materials: Material[];
  total: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: { code: string; message: string } | null;
  meta: Record<string, unknown> | null;
}

async function unwrap<T>(response: Response): Promise<T> {
  const body: ApiEnvelope<T> = await response.json();
  if (!body.success) {
    throw new Error(body.error?.message ?? "Request failed");
  }
  return body.data as T;
}

export const api = {
  materials: {
    list: () =>
      fetch(`${API_BASE}/api/materials`).then((r) => unwrap<MaterialListData>(r)),

    upload: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return fetch(`${API_BASE}/api/materials`, {
        method: "POST",
        body: fd,
      }).then((r) => unwrap<Material>(r));
    },

    delete: (id: number) =>
      fetch(`${API_BASE}/api/materials/${id}`, { method: "DELETE" }).then((r) =>
        unwrap<unknown>(r),
      ),
  },

  quiz: {
    generate: (topic: string, difficulty: number, count: number) =>
      fetch(`${API_BASE}/api/quiz/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, difficulty, count }),
      }).then((r) => unwrap<QuizData>(r)),

    submit: (
      questionId: string,
      correctAnswer: string,
      studentAnswer: string,
      questionType: string,
    ) =>
      fetch(
        `${API_BASE}/api/quiz/submit?${new URLSearchParams({
          question_id: questionId,
          correct_answer: correctAnswer,
          student_answer: studentAnswer,
          question_type: questionType,
        })}`,
        { method: "POST" },
      ).then((r) => unwrap<ScoreResult>(r)),
  },

  review: {
    weakPoints: () =>
      fetch(`${API_BASE}/api/review/weak-points`).then((r) => unwrap<DashboardData>(r)),
  },
};

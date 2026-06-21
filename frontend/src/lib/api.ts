const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = {
  materials: {
    list: () => fetch(`${API_BASE}/api/materials`).then((r) => r.json()),
    upload: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return fetch(`${API_BASE}/api/materials`, {
        method: "POST",
        body: fd,
      }).then((r) => r.json());
    },
    delete: (id: number) =>
      fetch(`${API_BASE}/api/materials/${id}`, { method: "DELETE" }),
  },
  quiz: {
    generate: (topic: string, difficulty: number, count: number) =>
      fetch(`${API_BASE}/api/quiz/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, difficulty, count }),
      }).then((r) => r.json()),
    submit: (
      questionId: string,
      correctAnswer: string,
      studentAnswer: string,
      questionType: string
    ) =>
      fetch(
        `${API_BASE}/api/quiz/submit?${new URLSearchParams({
          question_id: questionId,
          correct_answer: correctAnswer,
          student_answer: studentAnswer,
          question_type: questionType,
        })}`,
        { method: "POST" }
      ).then((r) => r.json()),
  },
  review: {
    weakPoints: () =>
      fetch(`${API_BASE}/api/review/weak-points`).then((r) => r.json()),
  },
};

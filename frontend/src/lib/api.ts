import type {
  Conversation,
  ConversationListData,
  ConversationMessage,
  DashboardData,
  LearningProfile,
  Material,
  QuizData,
  ScoreResult,
} from "@/types";
import { API_BASE } from "@/lib/config";

interface MaterialListData {
  materials: Material[];
  total: number;
}

interface ConversationMessagesData {
  conversation_id: number;
  messages: ConversationMessage[];
}

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
  conversations: {
    active: () =>
      fetch(`${API_BASE}/api/conversations/active`).then((r) =>
        unwrap<Conversation>(r),
      ),

    list: () =>
      fetch(`${API_BASE}/api/conversations`).then((r) =>
        unwrap<ConversationListData>(r),
      ),

    create: () =>
      fetch(`${API_BASE}/api/conversations`, { method: "POST" }).then((r) =>
        unwrap<Conversation>(r),
      ),

    delete: (id: number) =>
      fetch(`${API_BASE}/api/conversations/${id}`, { method: "DELETE" }).then(
        (r) => unwrap<unknown>(r),
      ),

    messages: (id: number) =>
      fetch(`${API_BASE}/api/conversations/${id}/messages`).then((r) =>
        unwrap<ConversationMessagesData>(r),
      ),
  },

  materials: {
    list: () =>
      fetch(`${API_BASE}/api/materials`).then((r) =>
        unwrap<MaterialListData>(r),
      ),

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
      fetch(`${API_BASE}/api/review/weak-points`).then((r) =>
        unwrap<DashboardData>(r),
      ),
  },

  memory: {
    profile: () =>
      fetch(`${API_BASE}/api/memory/profile`).then((r) =>
        unwrap<LearningProfile>(r),
      ),
  },
};

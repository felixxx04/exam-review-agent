import type {
  Conversation,
  ConversationListData,
  ConversationMessage,
  DailySessionData,
  DashboardData,
  LearningProfile,
  Material,
  MistakeExportData,
  MistakeExplanationData,
  MistakeListData,
  MistakeUpdatePayload,
  QuizData,
  ReviewMistake,
  ScoreResult,
  StudyPlanData,
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

interface QuizSubmitPayload {
  questionId: string;
  correctAnswer: string;
  studentAnswer: string;
  questionType: string;
  concept: string;
  topic: string;
  questionText: string;
  explanation: string;
  sourceChunkIds: string[];
  sourceMaterial: string | null;
}

interface MistakeListParams {
  status?: string;
  concept?: string;
  topic?: string;
  question_type?: string;
  search?: string;
  sort?: string;
  limit?: number;
  offset?: number;
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

    submit: (payload: QuizSubmitPayload) =>
      fetch(`${API_BASE}/api/quiz/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question_id: payload.questionId,
          correct_answer: payload.correctAnswer,
          student_answer: payload.studentAnswer,
          question_type: payload.questionType,
          concept: payload.concept,
          topic: payload.topic,
          question_text: payload.questionText,
          explanation: payload.explanation,
          source_chunk_ids: payload.sourceChunkIds,
          source_material: payload.sourceMaterial,
        }),
      }).then((r) => unwrap<ScoreResult>(r)),
  },

  review: {
    weakPoints: () =>
      fetch(`${API_BASE}/api/review/weak-points`).then((r) =>
        unwrap<DashboardData>(r),
      ),

    mistakes: (params: MistakeListParams = {}) => {
      const search = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== "" && value !== null) {
          search.set(key, String(value));
        }
      });
      const query = search.toString();
      return fetch(`${API_BASE}/api/review/mistakes${query ? `?${query}` : ""}`).then((r) =>
        unwrap<MistakeListData>(r),
      );
    },

    mistake: (id: string) =>
      fetch(`${API_BASE}/api/review/mistakes/${id}`).then((r) =>
        unwrap<ReviewMistake>(r),
      ),

    updateMistake: (id: string, payload: MistakeUpdatePayload) =>
      fetch(`${API_BASE}/api/review/mistakes/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then((r) => unwrap<ReviewMistake>(r)),

    dailySession: (payload: { limit: number }) =>
      fetch(`${API_BASE}/api/review/daily-session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then((r) => unwrap<DailySessionData>(r)),

    similarQuiz: (id: string) =>
      fetch(`${API_BASE}/api/review/mistakes/${id}/similar-quiz`, {
        method: "POST",
      }).then((r) => unwrap<QuizData>(r)),

    explainMistake: (id: string) =>
      fetch(`${API_BASE}/api/review/mistakes/${id}/explanation`, {
        method: "POST",
      }).then((r) => unwrap<MistakeExplanationData>(r)),

    studyPlan: (payload: { exam_date: string; days_before_exam: number }) =>
      fetch(`${API_BASE}/api/review/study-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then((r) => unwrap<StudyPlanData>(r)),

    exportMistakes: (params: { format: "markdown" | "csv" }) =>
      fetch(`${API_BASE}/api/review/export?${new URLSearchParams(params)}`).then((r) =>
        unwrap<MistakeExportData>(r),
      ),
  },

  memory: {
    profile: () =>
      fetch(`${API_BASE}/api/memory/profile`).then((r) =>
        unwrap<LearningProfile>(r),
      ),
  },
};

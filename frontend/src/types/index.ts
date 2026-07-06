export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  quiz?: QuizData;
  dashboard?: DashboardData;
  timestamp: number;
}

export interface Citation {
  source: string;
  page?: number;
  chunk_id?: string;
}

export interface QuizQuestion {
  id: string;
  question: string;
  question_type: "multiple_choice" | "fill_blank";
  options?: string[];
  correct: string;
  explanation?: string;
  difficulty: number;
  topic: string;
  source_chunk_ids: string[];
}

export interface QuizData {
  questions: QuizQuestion[];
  topic: string;
  total: number;
}

export interface Material {
  id: number;
  filename: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  page_count: number;
  processing_status: "pending" | "processing" | "ready" | "failed";
  chunk_count: number | null;
  error_message: string | null;
  storage_path?: string | null;
  mime_type?: string | null;
  hash?: string | null;
  processed_at?: string | null;
  parse_error?: string | null;
  created_at: string;
}

export interface Conversation {
  id: number;
  title: string;
  summary: string | null;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationListData {
  conversations: Conversation[];
  total: number;
}

export interface ConversationMessage {
  id: number;
  conversation_id: number;
  role: "user" | "assistant" | "system";
  content: string;
  material_scope: string[] | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface LearningProfile {
  current_subject: string | null;
  review_goal: string | null;
  weak_concepts: string[];
  frequent_questions: string[];
  active_materials: string[];
  preferences: Record<string, unknown>;
  updated_at: string;
}

export interface WeakConcept {
  concept: string;
  topic: string;
  accuracy: number;
  attempt_count: number;
}

export interface DashboardData {
  weak_concepts: WeakConcept[];
  total_questions: number;
  accuracy: number;
}

export type ReviewMistakeStatus =
  | "unreviewed"
  | "corrected"
  | "needs_requiz"
  | "mastered";

export interface ReviewMistake {
  id: string;
  question_id: string;
  question_text: string;
  question_type: "multiple_choice" | "fill_blank" | string;
  concept: string;
  topic: string;
  wrong_answer: string;
  correct_answer: string;
  explanation: string | null;
  source_material: string | null;
  source_chunk_ids: string[];
  status: ReviewMistakeStatus;
  attempt_count: number;
  last_wrong_at: string;
  correction_note: string;
  mastered_at: string | null;
  next_review_at: string | null;
  review_history: Array<Record<string, unknown>>;
}

export interface ReviewSummary {
  total_count: number;
  pending_count: number;
  mastered_count: number;
  corrected_count: number;
  needs_requiz_count: number;
}

export interface MistakeListData {
  mistakes: ReviewMistake[];
  summary: ReviewSummary;
  total: number;
}

export interface MistakeUpdatePayload {
  correction_note?: string;
  status?: ReviewMistakeStatus;
  mastered?: boolean;
}

export interface DailySessionData {
  mistakes: ReviewMistake[];
  total: number;
  message: string;
}

export interface MistakeExplanationData {
  explanation: string;
}

export interface StudyPlanDay {
  day: number;
  topics: string[];
  tasks: string[];
}

export interface StudyPlanData {
  plan: StudyPlanDay[];
  message: string;
}

export interface MistakeExportData {
  format: string;
  filename: string;
  content: string;
}

export type AppMode = "ask" | "quiz" | "review";

export interface ScoreResult {
  is_correct: boolean;
  mistake_recorded: boolean;
  score: number;
  feedback: string;
}

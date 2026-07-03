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
  page: number;
  chunk_id: string;
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

export type AppMode = "ask" | "quiz" | "review";

export interface ScoreResult {
  is_correct: boolean;
  mistake_recorded: boolean;
  score: number;
  feedback: string;
}

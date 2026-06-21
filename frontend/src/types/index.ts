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
  created_at: string;
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

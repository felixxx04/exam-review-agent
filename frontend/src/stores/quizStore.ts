import { create } from "zustand";
import type { QuizQuestion, ScoreResult } from "@/types";

interface QuizState {
  questions: QuizQuestion[];
  currentIndex: number;
  answers: Record<string, string>;
  scores: Record<string, ScoreResult>;
  isGenerating: boolean;
  topic: string;
  setQuestions: (questions: QuizQuestion[], topic?: string) => void;
  answerQuestion: (questionId: string, answer: string) => void;
  recordScore: (questionId: string, result: ScoreResult) => void;
  nextQuestion: () => void;
  prevQuestion: () => void;
  resetQuiz: () => void;
  setGenerating: (v: boolean) => void;
}

export const useQuizStore = create<QuizState>((set) => ({
  questions: [],
  currentIndex: 0,
  answers: {},
  scores: {},
  isGenerating: false,
  topic: "",
  setQuestions: (questions, topic = "") =>
    set({ questions, topic, currentIndex: 0, answers: {}, scores: {} }),
  answerQuestion: (questionId, answer) =>
    set((s) => ({ answers: { ...s.answers, [questionId]: answer } })),
  recordScore: (questionId, result) =>
    set((s) => ({ scores: { ...s.scores, [questionId]: result } })),
  nextQuestion: () =>
    set((s) => ({
      currentIndex: Math.min(s.currentIndex + 1, s.questions.length - 1),
    })),
  prevQuestion: () =>
    set((s) => ({ currentIndex: Math.max(s.currentIndex - 1, 0) })),
  resetQuiz: () =>
    set({
      questions: [],
      currentIndex: 0,
      answers: {},
      scores: {},
      topic: "",
    }),
  setGenerating: (v) => set({ isGenerating: v }),
}));

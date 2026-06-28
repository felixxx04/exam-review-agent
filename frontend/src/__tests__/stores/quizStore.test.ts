import { describe, it, expect, beforeEach } from "vitest";
import { useQuizStore } from "@/stores/quizStore";
import type { QuizQuestion, ScoreResult } from "@/types";

const sampleQuestions: QuizQuestion[] = [
  {
    id: "q1",
    question: "What is 2+2?",
    question_type: "multiple_choice",
    options: ["A. 3", "B. 4", "C. 5", "D. 6"],
    correct: "B",
    explanation: "2+2=4",
    difficulty: 1,
    topic: "math",
    source_chunk_ids: [],
  },
  {
    id: "q2",
    question: "Fill: Hello ___",
    question_type: "fill_blank",
    options: [],
    correct: "world",
    explanation: "Common phrase",
    difficulty: 2,
    topic: "english",
    source_chunk_ids: [],
  },
];

const sampleScore: ScoreResult = {
  is_correct: true,
  mistake_recorded: false,
  score: 1.0,
  feedback: "Great!",
};

describe("quizStore", () => {
  beforeEach(() => {
    useQuizStore.setState({
      questions: [],
      currentIndex: 0,
      answers: {},
      scores: {},
    });
  });

  it("sets questions and resets state", () => {
    useQuizStore.getState().setQuestions(sampleQuestions);
    const s = useQuizStore.getState();
    expect(s.questions).toHaveLength(2);
    expect(s.currentIndex).toBe(0);
  });

  it("records an answer", () => {
    useQuizStore.getState().setQuestions(sampleQuestions);
    useQuizStore.getState().answerQuestion("q1", "B");
    expect(useQuizStore.getState().answers["q1"]).toBe("B");
  });

  it("records a score", () => {
    useQuizStore.getState().setQuestions(sampleQuestions);
    useQuizStore.getState().answerQuestion("q1", "B");
    useQuizStore.getState().recordScore("q1", sampleScore);
    expect(useQuizStore.getState().scores["q1"]).toBe(sampleScore);
  });

  it("navigates to next question", () => {
    useQuizStore.getState().setQuestions(sampleQuestions);
    useQuizStore.getState().nextQuestion();
    expect(useQuizStore.getState().currentIndex).toBe(1);
  });

  it("does not go past last question", () => {
    useQuizStore.getState().setQuestions(sampleQuestions);
    useQuizStore.getState().nextQuestion();
    useQuizStore.getState().nextQuestion();
    expect(useQuizStore.getState().currentIndex).toBe(1);
  });

  it("navigates to previous question", () => {
    useQuizStore.getState().setQuestions(sampleQuestions);
    useQuizStore.getState().nextQuestion();
    useQuizStore.getState().prevQuestion();
    expect(useQuizStore.getState().currentIndex).toBe(0);
  });

  it("does not go before first question", () => {
    useQuizStore.getState().setQuestions(sampleQuestions);
    useQuizStore.getState().prevQuestion();
    expect(useQuizStore.getState().currentIndex).toBe(0);
  });

  it("resets quiz", () => {
    useQuizStore.getState().setQuestions(sampleQuestions);
    useQuizStore.getState().answerQuestion("q1", "B");
    useQuizStore.getState().resetQuiz();
    expect(useQuizStore.getState().questions).toHaveLength(0);
    expect(Object.keys(useQuizStore.getState().answers)).toHaveLength(0);
  });
});

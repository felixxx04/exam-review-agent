import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QuizCard } from "@/components/QuizCard";
import { useChatStore } from "@/stores/chatStore";
import { useQuizStore } from "@/stores/quizStore";
import type { QuizQuestion } from "@/types";

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
];

describe("QuizCard", () => {
  beforeEach(() => {
    useQuizStore.setState({
      questions: [],
      currentIndex: 0,
      answers: {},
      scores: {},
    });
    useChatStore.setState({ mode: "quiz" });
  });

  it("shows empty state when no questions", () => {
    render(<QuizCard />);
    expect(screen.getByText(/开始一次测验/)).toBeInTheDocument();
  });

  it("does not render when mode is not quiz", () => {
    useChatStore.setState({ mode: "ask" });
    const { container } = render(<QuizCard />);
    expect(container.innerHTML).toBe("");
  });

  it("renders question and options", () => {
    useQuizStore.setState({ questions: sampleQuestions });
    render(<QuizCard />);
    expect(screen.getByText("What is 2+2?")).toBeInTheDocument();
    expect(screen.getByText("A. 3")).toBeInTheDocument();
    expect(screen.getByText("B. 4")).toBeInTheDocument();
    expect(screen.getByText(/第 1 题/)).toBeInTheDocument();
  });

  it("shows progress indicator", () => {
    useQuizStore.setState({ questions: sampleQuestions });
    render(<QuizCard />);
    expect(screen.getByText(/第 1 题.*共 1 题/)).toBeInTheDocument();
  });
});

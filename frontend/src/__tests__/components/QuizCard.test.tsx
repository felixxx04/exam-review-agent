import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuizCard } from "@/components/QuizCard";
import { api } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";
import { useQuizStore } from "@/stores/quizStore";
import type { QuizQuestion } from "@/types";

vi.mock("@/lib/api", () => ({
  api: {
    quiz: {
      submit: vi.fn(),
    },
  },
}));

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
    vi.mocked(api.quiz.submit).mockReset();
    vi.mocked(api.quiz.submit).mockResolvedValue({
      is_correct: false,
      mistake_recorded: true,
      score: 0,
      feedback: "",
    });
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

  it("submits the selected answer with question context", async () => {
    const user = userEvent.setup();
    useQuizStore.setState({ questions: sampleQuestions });

    render(<QuizCard />);

    await user.click(screen.getByRole("button", { name: /A\. 3/ }));
    await user.click(screen.getByRole("button", { name: /提交答案/ }));

    expect(api.quiz.submit).toHaveBeenCalledWith({
      questionId: "q1",
      correctAnswer: "B",
      studentAnswer: "A",
      questionType: "multiple_choice",
      concept: "math",
      topic: "math",
      questionText: "What is 2+2?",
      explanation: "2+2=4",
      sourceChunkIds: [],
      sourceMaterial: null,
    });
  });
});

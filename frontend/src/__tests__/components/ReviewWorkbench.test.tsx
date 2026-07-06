import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReviewWorkbench } from "@/components/review/ReviewWorkbench";
import { api } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";
import { useQuizStore } from "@/stores/quizStore";
import type { MistakeListData, ReviewMistake, WeakConcept } from "@/types";

vi.mock("@/lib/api", () => ({
  api: {
    review: {
      weakPoints: vi.fn(),
      mistakes: vi.fn(),
      updateMistake: vi.fn(),
      dailySession: vi.fn(),
      similarQuiz: vi.fn(),
      explainMistake: vi.fn(),
      studyPlan: vi.fn(),
      exportMistakes: vi.fn(),
    },
    quiz: {
      generate: vi.fn(),
    },
  },
}));

const weakConcepts: WeakConcept[] = [
  {
    concept: "特征值",
    topic: "线性代数",
    accuracy: 0,
    attempt_count: 2,
  },
];

const mistakes: ReviewMistake[] = [
  {
    id: "m1",
    question_id: "q1",
    question_text: "矩阵 A 的特征值定义是什么？",
    question_type: "multiple_choice",
    concept: "特征值",
    topic: "线性代数",
    wrong_answer: "A",
    correct_answer: "B",
    explanation: "特征值满足 Ax = λx。",
    source_material: "linear.pdf",
    source_chunk_ids: ["chunk-1"],
    status: "unreviewed",
    attempt_count: 2,
    last_wrong_at: "2026-07-06T10:00:00+00:00",
    correction_note: "",
    mastered_at: null,
    next_review_at: null,
    review_history: [{ event: "corrected", at: "2026-07-06T10:20:00+00:00" }],
  },
];

const mistakeList: MistakeListData = {
  mistakes,
  total: 1,
  summary: {
    total_count: 1,
    pending_count: 1,
    mastered_count: 0,
    corrected_count: 0,
    needs_requiz_count: 0,
  },
};

describe("ReviewWorkbench", () => {
  beforeEach(() => {
    useChatStore.setState({ mode: "review" });
    useQuizStore.setState({
      questions: [],
      currentIndex: 0,
      answers: {},
      scores: {},
      isGenerating: false,
      topic: "",
    });
    vi.mocked(api.review.weakPoints).mockReset();
    vi.mocked(api.review.mistakes).mockReset();
    vi.mocked(api.review.updateMistake).mockReset();
    vi.mocked(api.review.dailySession).mockReset();
    vi.mocked(api.review.similarQuiz).mockReset();
    vi.mocked(api.review.explainMistake).mockReset();
    vi.mocked(api.review.studyPlan).mockReset();
    vi.mocked(api.review.exportMistakes).mockReset();
    vi.mocked(api.quiz.generate).mockReset();
    vi.mocked(api.review.weakPoints).mockResolvedValue({
      weak_concepts: weakConcepts,
      total_questions: 1,
      accuracy: 0,
    });
    vi.mocked(api.review.mistakes).mockResolvedValue(mistakeList);
    vi.mocked(api.review.updateMistake).mockResolvedValue({
      ...mistakes[0],
      status: "corrected",
      correction_note: "我把定义和计算公式混淆了。",
    });
    vi.mocked(api.review.dailySession).mockResolvedValue({
      mistakes,
      total: 1,
      message: "今日复习已准备好",
    });
    vi.mocked(api.review.similarQuiz).mockResolvedValue({
      questions: [],
      topic: "特征值",
      total: 0,
    });
    vi.mocked(api.review.explainMistake).mockResolvedValue({
      explanation: "正确答案是 B。你的答案是 A。",
    });
    vi.mocked(api.review.studyPlan).mockResolvedValue({
      plan: [{ day: 1, topics: ["特征值"], tasks: ["重做错题"] }],
      message: "已生成复习计划",
    });
    vi.mocked(api.review.exportMistakes).mockResolvedValue({
      format: "markdown",
      filename: "mistakes.md",
      content: "# 错题导出\n\n## 特征值定义",
    });
    vi.mocked(api.quiz.generate).mockResolvedValue({
      questions: [],
      topic: "特征值",
      total: 0,
    });
  });

  it("renders mistakes, summary, and detail actions", async () => {
    render(<ReviewWorkbench />);

    expect(await screen.findByText("待复习错题")).toBeInTheDocument();
    expect(screen.getAllByText("矩阵 A 的特征值定义是什么？").length).toBeGreaterThan(0);
    expect(screen.getByText("错误答案")).toBeInTheDocument();
    expect(screen.getByText(/复习历史/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /保存订正/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /标记已掌握/ })).toBeInTheDocument();
  });

  it("saves a correction note", async () => {
    const user = userEvent.setup();
    render(<ReviewWorkbench />);

    const note = await screen.findByLabelText("订正笔记");
    await user.type(note, "我把定义和计算公式混淆了。");
    await user.click(screen.getByRole("button", { name: /保存订正/ }));

    await waitFor(() => {
      expect(api.review.updateMistake).toHaveBeenCalledWith("m1", {
        correction_note: "我把定义和计算公式混淆了。",
        status: "corrected",
      });
    });
  });

  it("marks a mistake as mastered", async () => {
    const user = userEvent.setup();
    vi.mocked(api.review.updateMistake).mockResolvedValue({
      ...mistakes[0],
      status: "mastered",
      mastered_at: "2026-07-06T10:30:00+00:00",
    });

    render(<ReviewWorkbench />);

    await user.click(await screen.findByRole("button", { name: /标记已掌握/ }));

    await waitFor(() => {
      expect(api.review.updateMistake).toHaveBeenCalledWith("m1", {
        mastered: true,
      });
    });
  });

  it("starts a concept retest from a weak concept", async () => {
    const user = userEvent.setup();
    render(<ReviewWorkbench />);

    await user.click(await screen.findByRole("button", { name: /再测 特征值/ }));

    expect(api.quiz.generate).toHaveBeenCalledWith("特征值", 0.3, 3);
    expect(useChatStore.getState().mode).toBe("quiz");
  });

  it("starts a daily review flow", async () => {
    const user = userEvent.setup();
    render(<ReviewWorkbench />);

    await user.click(await screen.findByRole("button", { name: /开始今日复习/ }));

    expect(api.review.dailySession).toHaveBeenCalledWith({ limit: 5 });
    expect(await screen.findByText("今日复习 1 / 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /显示答案/ })).toBeInTheDocument();
  });

  it("generates a similar quiz from the selected mistake", async () => {
    const user = userEvent.setup();
    render(<ReviewWorkbench />);

    await user.click(await screen.findByRole("button", { name: /生成相似题/ }));

    expect(api.review.similarQuiz).toHaveBeenCalledWith("m1");
    expect(useChatStore.getState().mode).toBe("quiz");
  });

  it("generates an explanation for the selected mistake", async () => {
    const user = userEvent.setup();
    render(<ReviewWorkbench />);

    await user.click(await screen.findByRole("button", { name: /生成错因分析/ }));

    expect(api.review.explainMistake).toHaveBeenCalledWith("m1");
    expect(await screen.findByText(/正确答案是 B/)).toBeInTheDocument();
  });

  it("generates a study plan", async () => {
    const user = userEvent.setup();
    render(<ReviewWorkbench />);

    await user.click(await screen.findByRole("button", { name: /生成复习计划/ }));
    await user.click(screen.getByRole("button", { name: /确认生成/ }));

    expect(api.review.studyPlan).toHaveBeenCalled();
    expect(await screen.findByText("第 1 天")).toBeInTheDocument();
    expect(screen.getByText("重做错题")).toBeInTheDocument();
  });

  it("exports mistakes as markdown", async () => {
    const user = userEvent.setup();
    render(<ReviewWorkbench />);

    await user.click(await screen.findByRole("button", { name: /导出 Markdown/ }));

    expect(api.review.exportMistakes).toHaveBeenCalledWith({ format: "markdown" });
    expect(await screen.findByText(/# 错题导出/)).toBeInTheDocument();
  });
});

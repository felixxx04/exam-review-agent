import { describe, expect, it } from "vitest";
import { getQuizOptionState } from "@/lib/quizOptionState";

describe("getQuizOptionState", () => {
  it("marks the selected option before submission", () => {
    expect(
      getQuizOptionState({
        option: "B. 4",
        selected: "B",
        correct: "B",
        isSubmitted: false,
      }),
    ).toEqual({
      letter: "B",
      isSelected: true,
      isCorrect: false,
      isWrong: false,
      background: "var(--color-primary-subtle)",
      border: "var(--color-primary)",
      textColor: "var(--color-primary)",
    });
  });

  it("marks correct and wrong answers after submission", () => {
    expect(
      getQuizOptionState({
        option: "B. 4",
        selected: "A",
        correct: "B",
        isSubmitted: true,
      }),
    ).toMatchObject({
      isCorrect: true,
      isWrong: false,
      background: "var(--color-success-subtle)",
      border: "var(--color-success)",
      textColor: "var(--color-success)",
    });

    expect(
      getQuizOptionState({
        option: "A. 3",
        selected: "A",
        correct: "B",
        isSubmitted: true,
      }),
    ).toMatchObject({
      isCorrect: false,
      isWrong: true,
      background: "var(--color-error-subtle)",
      border: "var(--color-error)",
      textColor: "var(--color-error)",
    });
  });

  it("leaves neutral options unchanged", () => {
    expect(
      getQuizOptionState({
        option: "C. 5",
        selected: "A",
        correct: "B",
        isSubmitted: false,
      }),
    ).toMatchObject({
      isSelected: false,
      isCorrect: false,
      isWrong: false,
      background: "transparent",
      border: "var(--color-border)",
      textColor: "var(--color-ink)",
    });
  });
});

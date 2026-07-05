interface QuizOptionStateInput {
  option: string;
  selected: string | undefined;
  correct: string;
  isSubmitted: boolean;
}

export function getQuizOptionState({
  option,
  selected,
  correct,
  isSubmitted,
}: QuizOptionStateInput) {
  const letter = option.charAt(0);
  const isSelected = selected === letter;
  const isCorrect = isSubmitted && letter === correct;
  const isWrong = isSubmitted && isSelected && letter !== correct;

  if (isCorrect) {
    return {
      letter,
      isSelected,
      isCorrect,
      isWrong,
      background: "var(--color-success-subtle)",
      border: "var(--color-success)",
      textColor: "var(--color-success)",
    };
  }

  if (isWrong) {
    return {
      letter,
      isSelected,
      isCorrect,
      isWrong,
      background: "var(--color-error-subtle)",
      border: "var(--color-error)",
      textColor: "var(--color-error)",
    };
  }

  if (isSelected) {
    return {
      letter,
      isSelected,
      isCorrect,
      isWrong,
      background: "var(--color-primary-subtle)",
      border: "var(--color-primary)",
      textColor: "var(--color-primary)",
    };
  }

  return {
    letter,
    isSelected,
    isCorrect,
    isWrong,
    background: "transparent",
    border: "var(--color-border)",
    textColor: "var(--color-ink)",
  };
}

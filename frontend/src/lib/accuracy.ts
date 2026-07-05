export function getAccuracyColor(accuracy: number) {
  if (accuracy >= 0.6) return "var(--color-success)";
  if (accuracy >= 0.4) return "var(--color-accent)";
  return "var(--color-error)";
}

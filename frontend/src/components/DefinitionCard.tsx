"use client";

interface DefinitionCardProps {
  term: string;
  definition: string;
  source?: string;
}

export function DefinitionCard({ term, definition, source }: DefinitionCardProps) {
  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-4">
      <p className="text-base font-bold mb-2">{term}</p>
      <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{definition}</p>
      {source && (
        <p className="mt-2 text-xs text-[var(--text-secondary)]">Source: {source}</p>
      )}
    </div>
  );
}

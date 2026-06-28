"use client";

interface DefinitionCardProps {
  term: string;
  definition: string;
  source?: string;
}

export function DefinitionCard({ term, definition, source }: DefinitionCardProps) {
  return (
    <div
      className="p-4"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-xl)",
      }}
    >
      <p
        className="mb-2 font-semibold"
        style={{
          fontFamily: "var(--font-prose)",
          fontSize: "var(--text-base)",
          color: "var(--color-primary)",
          lineHeight: "var(--leading-tight)",
        }}
      >
        {term}
      </p>
      <p
        className="text-sm"
        style={{
          fontFamily: "var(--font-prose)",
          color: "var(--color-ink)",
          lineHeight: "var(--leading-prose)",
        }}
      >
        {definition}
      </p>
      {source && (
        <p
          className="mt-2 text-xs"
          style={{ color: "var(--color-muted)" }}
        >
          来源: {source}
        </p>
      )}
    </div>
  );
}

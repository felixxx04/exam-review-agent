"use client";

import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  description: string;
  headingLevel?: 2 | 3;
  padding?: string;
  iconMarginBottom?: string;
  titleFontSize?: string;
  maxWidth?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  headingLevel = 3,
  padding = "var(--space-5)",
  iconMarginBottom = "var(--space-6)",
  titleFontSize = "var(--text-xl)",
  maxWidth = "360px",
}: EmptyStateProps) {
  const Heading = headingLevel === 2 ? "h2" : "h3";

  return (
    <div className="text-center" style={{ padding }}>
      <div
        className="mx-auto flex items-center justify-center"
        style={{
          width: "72px",
          height: "72px",
          borderRadius: "var(--radius-xl)",
          background: "var(--color-primary-subtle)",
          marginBottom: iconMarginBottom,
        }}
      >
        {icon}
      </div>
      <Heading
        style={{
          fontFamily: "var(--font-prose)",
          fontSize: titleFontSize,
          fontWeight: 600,
          color: "var(--color-ink)",
          lineHeight: "var(--leading-tight)",
          marginBottom: "var(--space-2)",
        }}
      >
        {title}
      </Heading>
      <p
        className="mx-auto"
        style={{
          color: "var(--color-muted)",
          fontSize: "var(--text-base)",
          lineHeight: "var(--leading-prose)",
          maxWidth,
        }}
      >
        {description}
      </p>
    </div>
  );
}

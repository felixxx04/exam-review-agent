"use client";

import { useChatStore } from "@/stores/chatStore";
import { BookOpen, MessageCircle, BarChart3 } from "lucide-react";
import type { AppMode } from "@/types";

const modes: { key: AppMode; label: string; icon: React.ReactNode }[] = [
  { key: "ask", label: "问答", icon: <MessageCircle size={16} /> },
  { key: "quiz", label: "测验", icon: <BookOpen size={16} /> },
  { key: "review", label: "复习", icon: <BarChart3 size={16} /> },
];

export function Header() {
  const { mode, setMode } = useChatStore();

  return (
    <header
      className="border-b sticky top-0 z-10"
      style={{
        borderColor: "var(--color-border)",
        background: "var(--color-bg)",
        height: "var(--header-h)",
      }}
    >
      <div
        className="mx-auto flex items-center justify-between h-full px-4 sm:px-5"
        style={{ maxWidth: "var(--content-max)" }}
      >
        <h1
          className="text-base sm:text-lg font-semibold select-none shrink-0"
          style={{
            fontFamily: "var(--font-prose)",
            color: "var(--color-primary)",
            letterSpacing: "var(--tracking-tight)",
          }}
        >
          Exam Review
        </h1>

        <nav
          className="flex gap-0.5 sm:gap-1"
          role="tablist"
          aria-label="功能模式切换"
        >
          {modes.map((m, i) => {
            const active = mode === m.key;
            return (
              <button
                key={m.key}
                role="tab"
                aria-selected={active}
                tabIndex={active ? 0 : -1}
                onClick={() => setMode(m.key)}
                onKeyDown={(e) => {
                  const dirs: Record<string, number> = {
                    ArrowRight: 1,
                    ArrowLeft: -1,
                  };
                  if (dirs[e.key] !== undefined) {
                    e.preventDefault();
                    const next = (i + dirs[e.key] + modes.length) % modes.length;
                    setMode(modes[next].key);
                  }
                }}
                className="flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1.5 text-sm font-medium transition-colors"
                style={{
                  borderRadius: "var(--radius-md)",
                  background: active ? "var(--color-primary)" : "transparent",
                  color: active ? "oklch(1 0 0)" : "var(--color-muted)",
                  cursor: "pointer",
                }}
                onMouseEnter={(e) => {
                  if (!active) {
                    e.currentTarget.style.background = "var(--color-surface)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!active) {
                    e.currentTarget.style.background = "transparent";
                  }
                }}
              >
                {m.icon}
                {m.label}
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
}

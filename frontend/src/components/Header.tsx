"use client";

import { useChatStore } from "@/stores/chatStore";
import { useCreateConversation } from "@/hooks/useCreateConversation";
import { BarChart3, BookOpen, MessageCircle, Plus } from "lucide-react";
import type { AppMode } from "@/types";

const modes: { key: AppMode; label: string; icon: React.ReactNode }[] = [
  { key: "ask", label: "问答", icon: <MessageCircle size={16} /> },
  { key: "quiz", label: "测验", icon: <BookOpen size={16} /> },
  { key: "review", label: "复习", icon: <BarChart3 size={16} /> },
];

interface HeaderProps {
  onConversationChange?: () => void;
}

export function Header({ onConversationChange }: HeaderProps) {
  const { mode, isStreaming, setMode } = useChatStore();
  const handleNewConversation = useCreateConversation(onConversationChange);

  return (
    <header className="app-header">
      <div className="flex h-full items-center justify-between gap-4 px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <div className="brand-mark" aria-hidden="true">
            ER
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold text-[color:var(--color-ink)] sm:text-lg">
              Exam Review
            </h1>
            <p className="hidden text-xs text-[color:var(--color-muted)] sm:block">
              资料问答 · 自动测验 · 错题复习
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <nav
            className="mode-pill-nav"
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
                      const next =
                        (i + dirs[e.key] + modes.length) % modes.length;
                      setMode(modes[next].key);
                    }
                  }}
                  className="mode-pill"
                  data-active={active}
                >
                  {m.icon}
                  <span>{m.label}</span>
                </button>
              );
            })}
          </nav>

          <button
            type="button"
            onClick={handleNewConversation}
            disabled={isStreaming}
            className="primary-action"
          >
            <Plus size={16} />
            <span className="hidden sm:inline">新会话</span>
          </button>
        </div>
      </div>
    </header>
  );
}

"use client";

import { useChatStore } from "@/stores/chatStore";
import { BookOpen, MessageCircle, BarChart3 } from "lucide-react";
import type { AppMode } from "@/types";

const modes: { key: AppMode; label: string; icon: React.ReactNode }[] = [
  { key: "ask", label: "问答", icon: <MessageCircle size={18} /> },
  { key: "quiz", label: "测验", icon: <BookOpen size={18} /> },
  { key: "review", label: "复习", icon: <BarChart3 size={18} /> },
];

export function Header() {
  const { mode, setMode } = useChatStore();

  return (
    <header className="border-b border-[var(--border)] px-6 py-4">
      <div className="max-w-4xl mx-auto flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-tight">
          Exam Review
        </h1>
        <nav className="flex gap-1">
          {modes.map((m) => (
            <button
              key={m.key}
              onClick={() => setMode(m.key)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === m.key
                  ? "bg-[var(--accent)] text-white"
                  : "text-[var(--text-secondary)] hover:bg-[var(--surface)]"
              }`}
            >
              {m.icon}
              {m.label}
            </button>
          ))}
        </nav>
      </div>
    </header>
  );
}

"use client";

import { useChatStore } from "@/stores/chatStore";

export function MessageList() {
  const { messages } = useChatStore();

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-[var(--text-secondary)]">
        <div className="text-center">
          <p className="text-lg font-medium">开始你的复习之旅</p>
          <p className="text-sm mt-2">上传复习资料，然后提问或开始测验</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4">
      <div className="max-w-4xl mx-auto space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-[var(--accent)] text-white"
                  : "bg-[var(--surface)] text-[var(--text-primary)] border border-[var(--border)]"
              }`}
            >
              <div>{msg.content}</div>
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-2 pt-2 border-t border-[var(--border)] text-xs text-[var(--text-secondary)]">
                  {msg.citations.map((c, i) => (
                    <span key={i} className="inline-block mr-2">
                      {c.source}{c.page ? ` P.${c.page}` : ""}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

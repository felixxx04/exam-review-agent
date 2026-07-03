"use client";

import { useChatStore } from "@/stores/chatStore";

export function MessageList() {
  const { messages, isStreaming } = useChatStore();

  if (messages.length === 0) {
    return null;
  }

  return (
    <div className="message-list px-5 py-5">
      <div
        className="mx-auto space-y-4"
        style={{ maxWidth: "var(--content-max)" }}
      >
        {messages.map((msg, i) => {
          const isUser = msg.role === "user";
          const isLast = i === messages.length - 1;
          const showCursor = isStreaming && !isUser && isLast;

          return (
            <div
              key={msg.id}
              className={`flex ${isUser ? "justify-end" : "justify-start"}`}
            >
              <div
                className="max-w-[85%]"
                style={{
                  fontFamily: isUser ? "var(--font-ui)" : "var(--font-prose)",
                  fontSize: "var(--text-base)",
                  lineHeight: isUser
                    ? "var(--leading-ui)"
                    : "var(--leading-prose)",
                  padding: "var(--space-3) var(--space-4)",
                  borderRadius: isUser
                    ? "var(--radius-xl) var(--radius-xl) var(--radius-sm) var(--radius-xl)"
                    : "var(--radius-xl) var(--radius-xl) var(--radius-xl) var(--radius-sm)",
                  background: isUser
                    ? "var(--color-primary)"
                    : "var(--color-surface)",
                  color: isUser
                    ? "oklch(1 0 0)"
                    : "var(--color-ink)",
                  border: isUser
                    ? "none"
                    : "1px solid var(--color-border)",
                }}
              >
                <div className={showCursor ? "streaming-cursor" : ""}>
                  {msg.content}
                </div>

                {msg.citations && msg.citations.length > 0 && (
                  <div
                    className="mt-2 pt-2 text-xs flex flex-wrap gap-2"
                    style={{
                      borderTop: "1px solid var(--color-border)",
                      color: "var(--color-muted)",
                    }}
                  >
                    {msg.citations.map((c, ci) => (
                      <span
                        key={ci}
                        className="inline-flex items-center gap-1 px-1.5 py-0.5"
                        style={{
                          borderRadius: "var(--radius-sm)",
                          background: isUser
                            ? "oklch(1 0 0 / 0.15)"
                            : "var(--color-primary-subtle)",
                          color: isUser
                            ? "oklch(1 0 0)"
                            : "var(--color-primary)",
                          fontSize: "var(--text-xs)",
                        }}
                      >
                        {c.source}
                        {c.page ? ` P.${c.page}` : ""}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

"use client";

import { useChatStore } from "@/stores/chatStore";
import { BookOpen } from "lucide-react";

export function MessageList() {
  const { messages, isStreaming } = useChatStore();

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center px-5">
        <div
          className="text-center"
          style={{
            padding: "var(--space-5)",
          }}
        >
          <div
            className="mx-auto flex items-center justify-center"
            style={{
              width: "72px",
              height: "72px",
              borderRadius: "var(--radius-xl)",
              background: "var(--color-primary-subtle)",
              marginBottom: "var(--space-6)",
            }}
          >
            <BookOpen
              size={36}
              strokeWidth={1.2}
              style={{ color: "var(--color-primary)" }}
            />
          </div>
          <h2
            style={{
              fontFamily: "var(--font-prose)",
              fontSize: "var(--text-xl)",
              fontWeight: 600,
              color: "var(--color-ink)",
              lineHeight: "var(--leading-tight)",
              marginBottom: "var(--space-2)",
            }}
          >
            开始你的复习之旅
          </h2>
          <p
            className="mx-auto"
            style={{
              color: "var(--color-muted)",
              fontSize: "var(--text-base)",
              lineHeight: "var(--leading-prose)",
              maxWidth: "360px",
            }}
          >
            上传复习资料，然后直接提问、生成测验，或者查看薄弱知识点
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4">
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

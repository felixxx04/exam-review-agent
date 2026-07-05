"use client";

import { useEffect, useState } from "react";
import { useChatStore } from "@/stores/chatStore";

const THINKING_STEPS = [
  "理解你的问题",
  "检索相关资料",
  "组织回答结构",
  "准备生成答案",
];

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
          const showThinking = showCursor && msg.content.trim().length === 0;

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
                  color: isUser ? "oklch(1 0 0)" : "var(--color-ink)",
                  border: isUser ? "none" : "1px solid var(--color-border)",
                }}
              >
                {showThinking ? (
                  <AnswerThinking />
                ) : (
                  <div className={showCursor ? "streaming-cursor" : ""}>
                    {msg.content}
                  </div>
                )}

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

function AnswerThinking() {
  const [stepIndex, setStepIndex] = useState(0);
  const step = THINKING_STEPS[stepIndex];

  useEffect(() => {
    const id = window.setInterval(() => {
      setStepIndex((index) => (index + 1) % THINKING_STEPS.length);
    }, 1400);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="answer-thinking" role="status" aria-live="polite">
      <span className="thinking-core" aria-hidden="true">
        <span className="thinking-ring" />
        <span className="thinking-pulse" />
      </span>
      <span className="thinking-copy">
        <span className="thinking-title">Agent 正在准备回答</span>
        <span className="thinking-steps">
          <span className="thinking-step-text" key={step}>
            {step}
          </span>
        </span>
      </span>
    </div>
  );
}

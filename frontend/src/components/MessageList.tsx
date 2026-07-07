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
                className="message-bubble"
                data-role={isUser ? "user" : "assistant"}
                data-streaming={showCursor}
              >
                {showThinking ? (
                  <AnswerThinking />
                ) : (
                  <div className={showCursor ? "streaming-cursor" : ""}>
                    {msg.content}
                  </div>
                )}

                {msg.citations && msg.citations.length > 0 && (
                  <div className="message-citations">
                    {msg.citations.map((c, ci) => (
                      <span
                        key={ci}
                        className="citation-chip"
                        data-role={isUser ? "user" : "assistant"}
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

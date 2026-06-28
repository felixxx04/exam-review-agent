"use client";

import { useRef, useState } from "react";
import { useChatStream } from "@/hooks/useChatStream";
import { useChatStore } from "@/stores/chatStore";
import { Send, Square } from "lucide-react";

export function ChatInput() {
  const [text, setText] = useState("");
  const { sendMessage, abort } = useChatStream();
  const { isStreaming } = useChatStore();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    if (!text.trim() || isStreaming) return;
    sendMessage(text.trim());
    setText("");
    // Reset height after clearing
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    // Auto-resize
    const el = e.currentTarget;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !isStreaming) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const isDisabled = isStreaming;
  const isEmpty = !text.trim();

  return (
    <div
      className="border-t sticky bottom-0"
      style={{
        borderColor: "var(--color-border)",
        background: "var(--color-bg)",
        padding: "var(--space-4) var(--space-5)",
      }}
    >
      <div
        className="mx-auto flex gap-3 items-end"
        style={{ maxWidth: "var(--content-max)" }}
      >
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={isStreaming ? "等待回复..." : "输入你的问题..."}
          disabled={isDisabled}
          rows={1}
          className="flex-1 px-4 py-3 transition-colors resize-none"
          style={{
            borderRadius: "var(--radius-lg)",
            border: "1px solid var(--color-border)",
            background: "var(--color-surface)",
            color: "var(--color-ink)",
            fontFamily: "var(--font-prose)",
            fontSize: "var(--text-base)",
            lineHeight: "1.6",
            opacity: isDisabled ? 0.5 : 1,
            outline: "none",
            minHeight: "48px",
            maxHeight: "160px",
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = "var(--color-primary)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = "var(--color-border)";
          }}
          aria-label="输入问题"
        />
        <button
          onClick={isStreaming ? abort : handleSubmit}
          disabled={!isStreaming && isEmpty}
          className="flex items-center justify-center transition-colors shrink-0"
          style={{
            width: "48px",
            height: "48px",
            borderRadius: "var(--radius-lg)",
            background: isStreaming
              ? "var(--color-error)"
              : isEmpty
              ? "var(--color-surface)"
              : "var(--color-primary)",
            color: isStreaming
              ? "oklch(1 0 0)"
              : isEmpty
              ? "var(--color-muted)"
              : "oklch(1 0 0)",
            cursor: !isStreaming && isEmpty ? "not-allowed" : "pointer",
            border: "none",
          }}
          aria-label={isStreaming ? "停止生成" : "发送"}
        >
          {isStreaming ? <Square size={18} /> : <Send size={18} />}
        </button>
      </div>
    </div>
  );
}

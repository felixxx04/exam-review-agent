"use client";

import { useState } from "react";
import { useChatStream } from "@/hooks/useChatStream";
import { useChatStore } from "@/stores/chatStore";
import { Send, Square } from "lucide-react";

export function ChatInput() {
  const [text, setText] = useState("");
  const { sendMessage, abort } = useChatStream();
  const { isStreaming } = useChatStore();

  const handleSubmit = () => {
    if (!text.trim()) return;
    sendMessage(text.trim());
    setText("");
  };

  return (
    <div className="border-t border-[var(--border)] px-6 py-4 bg-[var(--bg)]">
      <div className="max-w-4xl mx-auto flex gap-3">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !isStreaming && handleSubmit()}
          placeholder={
            isStreaming ? "等待回复..." : "输入你的问题..."
          }
          disabled={isStreaming}
          className="flex-1 px-4 py-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] text-sm focus:outline-none focus:border-[var(--accent)] disabled:opacity-50"
        />
        <button
          onClick={isStreaming ? abort : handleSubmit}
          className={`px-4 py-3 rounded-xl text-sm font-medium transition-colors ${
            isStreaming
              ? "bg-[var(--error)] text-white"
              : "bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)]"
          }`}
        >
          {isStreaming ? <Square size={18} /> : <Send size={18} />}
        </button>
      </div>
    </div>
  );
}

"use client";

import { useRef, useState } from "react";
import { useChatStream } from "@/hooks/useChatStream";
import { useChatStore } from "@/stores/chatStore";
import { Send, Square } from "lucide-react";

interface ChatInputProps {
  onConversationChange?: () => void;
}

export function ChatInput({ onConversationChange }: ChatInputProps) {
  const [text, setText] = useState("");
  const { sendMessage, abort } = useChatStream({ onConversationChange });
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
    <div className="chat-input-dock">
      <div className="chat-input-shell">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={isStreaming ? "等待回复..." : "输入你的问题..."}
          disabled={isDisabled}
          rows={1}
          className="chat-textarea"
          style={{
            opacity: isDisabled ? 0.5 : 1,
          }}
          aria-label="输入问题"
        />
        <button
          onClick={isStreaming ? abort : handleSubmit}
          disabled={!isStreaming && isEmpty}
          className="chat-send-button"
          data-streaming={isStreaming}
          data-empty={isEmpty}
          aria-label={isStreaming ? "停止生成" : "发送"}
        >
          {isStreaming ? <Square size={18} /> : <Send size={18} />}
        </button>
      </div>
    </div>
  );
}

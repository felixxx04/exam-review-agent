import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageList } from "@/components/MessageList";
import { useChatStore } from "@/stores/chatStore";
import type { Message } from "@/types";

describe("MessageList", () => {
  beforeEach(() => {
    useChatStore.setState({
      messages: [],
      mode: "ask",
      isStreaming: false,
      materialScope: [],
    });
  });

  it("shows empty state when no messages", () => {
    render(<MessageList />);
    expect(screen.getByText(/开始你的复习之旅/)).toBeInTheDocument();
  });

  it("renders a user message", () => {
    const msg: Message = { id: "1", role: "user", content: "hello", timestamp: 0 };
    useChatStore.setState({ messages: [msg] });
    render(<MessageList />);
    expect(screen.getByText("hello")).toBeInTheDocument();
  });

  it("renders an assistant message with citations", () => {
    const msg: Message = {
      id: "2",
      role: "assistant",
      content: "reply",
      citations: [{ source: "test.pdf", page: 1, chunk_id: "c1" }],
      timestamp: 1,
    };
    useChatStore.setState({ messages: [msg] });
    render(<MessageList />);
    expect(screen.getByText("reply")).toBeInTheDocument();
    expect(screen.getByText(/test.pdf/)).toBeInTheDocument();
  });

  it("shows streaming cursor when streaming", () => {
    const msg: Message = { id: "1", role: "assistant", content: "partial", timestamp: 0 };
    useChatStore.setState({ messages: [msg], isStreaming: true });
    render(<MessageList />);
    const cursor = document.querySelector(".streaming-cursor");
    expect(cursor).toBeInTheDocument();
  });
});

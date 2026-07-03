import { describe, it, expect, beforeEach } from "vitest";
import { useChatStore } from "@/stores/chatStore";

const initialState = {
  messages: [],
  conversationId: null,
  mode: "ask" as const,
  isStreaming: false,
  materialScope: [] as string[],
};

describe("chatStore", () => {
  beforeEach(() => {
    useChatStore.setState(initialState);
  });

  it("adds a user message", () => {
    useChatStore.getState().addMessage({ id: "1", role: "user", content: "hello", timestamp: 0 });
    const msgs = useChatStore.getState().messages;
    expect(msgs).toHaveLength(1);
    expect(msgs[0].content).toBe("hello");
  });

  it("adds an assistant message", () => {
    useChatStore.getState().addMessage({ id: "2", role: "assistant", content: "reply", timestamp: 1 });
    expect(useChatStore.getState().messages[0].role).toBe("assistant");
  });

  it("sets mode", () => {
    useChatStore.getState().setMode("quiz");
    expect(useChatStore.getState().mode).toBe("quiz");
  });

  it("clears messages", () => {
    useChatStore.getState().addMessage({ id: "1", role: "user", content: "hi", timestamp: 0 });
    useChatStore.getState().clearMessages();
    expect(useChatStore.getState().messages).toHaveLength(0);
  });

  it("sets streaming state", () => {
    useChatStore.getState().setStreaming(true);
    expect(useChatStore.getState().isStreaming).toBe(true);
  });

  it("sets material scope", () => {
    useChatStore.getState().setMaterialScope(["file1.pdf"]);
    expect(useChatStore.getState().materialScope).toEqual(["file1.pdf"]);
  });

  it("messages are immutable (spread) on add", () => {
    useChatStore.getState().addMessage({ id: "a", role: "user", content: "first", timestamp: 0 });
    useChatStore.getState().addMessage({ id: "b", role: "assistant", content: "second", timestamp: 1 });
    expect(useChatStore.getState().messages).toHaveLength(2);
  });

  it("updates an existing message when ids match", () => {
    useChatStore.getState().addMessage({ id: "stream-1", role: "assistant", content: "QA", timestamp: 0 });
    useChatStore.getState().addMessage({
      id: "stream-1",
      role: "assistant",
      content: "QA handling in progress",
      timestamp: 0,
    });

    const msgs = useChatStore.getState().messages;
    expect(msgs).toHaveLength(1);
    expect(msgs[0].content).toBe("QA handling in progress");
  });

  it("stores conversation id and replaces restored messages", () => {
    useChatStore.getState().clearMessages();

    useChatStore.getState().setConversationId(42);
    useChatStore.getState().setMessages([
      {
        id: "m1",
        role: "user",
        content: "什么是幻读？",
        timestamp: 1,
      },
    ]);

    expect(useChatStore.getState().conversationId).toBe(42);
    expect(useChatStore.getState().messages).toHaveLength(1);
    expect(useChatStore.getState().messages[0].content).toBe("什么是幻读？");
  });

  it("starts a new conversation with empty ask-mode state", () => {
    useChatStore.setState({
      messages: [{ id: "old", role: "assistant", content: "旧消息", timestamp: 0 }],
      conversationId: 1,
      mode: "quiz",
      isStreaming: true,
      materialScope: ["MQ.docx"],
    });

    useChatStore.getState().startNewConversation(2);

    expect(useChatStore.getState().conversationId).toBe(2);
    expect(useChatStore.getState().messages).toEqual([]);
    expect(useChatStore.getState().mode).toBe("ask");
    expect(useChatStore.getState().isStreaming).toBe(false);
    expect(useChatStore.getState().materialScope).toEqual([]);
  });
});

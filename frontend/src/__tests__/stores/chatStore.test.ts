import { describe, it, expect, beforeEach } from "vitest";
import { useChatStore } from "@/stores/chatStore";

const initialState = {
  messages: [],
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
});

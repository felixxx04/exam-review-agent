import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Header } from "@/components/Header";
import { api } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";

vi.mock("@/lib/api", () => ({
  api: {
    conversations: {
      create: vi.fn(),
    },
  },
}));

describe("Header", () => {
  beforeEach(() => {
    useChatStore.setState({
      messages: [],
      conversationId: null,
      mode: "ask",
      isStreaming: false,
      materialScope: [],
    });
    vi.mocked(api.conversations.create).mockReset();
  });

  it("renders the app title and three mode buttons", () => {
    render(<Header />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "AI 学习工作台",
    );
    expect(screen.getByRole("button", { name: /新会话/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /问答/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /测验/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /复习/ })).toBeInTheDocument();
  });

  it("ask tab is selected by default", () => {
    render(<Header />);
    expect(screen.getByRole("tab", { name: /问答/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("clicking quiz tab changes mode", async () => {
    const user = userEvent.setup();
    render(<Header />);
    await user.click(screen.getByRole("tab", { name: /测验/ }));
    expect(useChatStore.getState().mode).toBe("quiz");
  });

  it("clicking review tab changes mode", async () => {
    const user = userEvent.setup();
    render(<Header />);
    await user.click(screen.getByRole("tab", { name: /复习/ }));
    expect(useChatStore.getState().mode).toBe("review");
  });

  it("clicking new conversation creates and switches to an empty conversation", async () => {
    const onConversationChange = vi.fn();
    vi.mocked(api.conversations.create).mockResolvedValue({
      id: 99,
      title: "新的复习会话",
      summary: null,
      message_count: 0,
      last_message_at: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    useChatStore.setState({
      messages: [{ id: "old", role: "user", content: "旧问题", timestamp: 0 }],
      conversationId: 1,
      mode: "quiz",
      isStreaming: false,
      materialScope: ["MQ.docx"],
    });

    const user = userEvent.setup();
    render(<Header onConversationChange={onConversationChange} />);
    await user.click(screen.getByRole("button", { name: /新会话/ }));

    expect(api.conversations.create).toHaveBeenCalledOnce();
    expect(useChatStore.getState().conversationId).toBe(99);
    expect(useChatStore.getState().messages).toEqual([]);
    expect(useChatStore.getState().mode).toBe("ask");
    expect(useChatStore.getState().materialScope).toEqual([]);
    expect(onConversationChange).toHaveBeenCalledOnce();
  });
});

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
      delete: vi.fn(),
      list: vi.fn(),
      messages: vi.fn(),
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
    vi.mocked(api.conversations.list).mockResolvedValue({
      conversations: [],
      total: 0,
    });
    vi.mocked(api.conversations.messages).mockResolvedValue({
      conversation_id: 1,
      messages: [],
    });
    vi.mocked(api.conversations.delete).mockResolvedValue({});
    vi.mocked(api.conversations.create).mockReset();
  });

  it("renders three mode buttons", () => {
    render(<Header />);
    expect(screen.getByRole("button", { name: /新会话/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /问答/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /测验/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /复习/ })).toBeInTheDocument();
  });

  it("renders the app title", () => {
    render(<Header />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Exam Review");
  });

  it("ask tab is selected by default", () => {
    render(<Header />);
    expect(screen.getByRole("tab", { name: /问答/ })).toHaveAttribute("aria-selected", "true");
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
    render(<Header />);
    await user.click(screen.getByRole("button", { name: /新会话/ }));

    expect(api.conversations.create).toHaveBeenCalledOnce();
    expect(useChatStore.getState().conversationId).toBe(99);
    expect(useChatStore.getState().messages).toEqual([]);
    expect(useChatStore.getState().mode).toBe("ask");
    expect(useChatStore.getState().materialScope).toEqual([]);
  });

  it("switches to a selected conversation from the conversation list", async () => {
    vi.mocked(api.conversations.list).mockResolvedValue({
      total: 2,
      conversations: [
        {
          id: 2,
          title: "新的复习会话",
          summary: null,
          message_count: 1,
          last_message_at: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: 1,
          title: "默认复习会话",
          summary: null,
          message_count: 0,
          last_message_at: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
    });
    vi.mocked(api.conversations.messages).mockResolvedValue({
      conversation_id: 2,
      messages: [
        {
          id: 10,
          conversation_id: 2,
          role: "user",
          content: "历史问题",
          material_scope: ["MQ.docx"],
          metadata: {},
          created_at: new Date(1).toISOString(),
        },
      ],
    });

    const user = userEvent.setup();
    render(<Header />);
    await user.click(screen.getByRole("button", { name: /会话列表/ }));
    await user.click(await screen.findByRole("button", { name: "会话 2" }));

    expect(useChatStore.getState().conversationId).toBe(2);
    expect(useChatStore.getState().messages[0].content).toBe("历史问题");
    expect(useChatStore.getState().materialScope).toEqual(["MQ.docx"]);
  });

  it("deletes a conversation and starts a clean fallback when no conversations remain", async () => {
    vi.mocked(api.conversations.list)
      .mockResolvedValueOnce({
        total: 1,
        conversations: [
          {
            id: 1,
            title: "默认复习会话",
            summary: null,
            message_count: 1,
            last_message_at: null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        ],
      })
      .mockResolvedValueOnce({ total: 0, conversations: [] });
    vi.mocked(api.conversations.create).mockResolvedValue({
      id: 3,
      title: "新的复习会话",
      summary: null,
      message_count: 0,
      last_message_at: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    vi.mocked(api.conversations.delete).mockResolvedValue({});
    useChatStore.setState({
      messages: [{ id: "old", role: "user", content: "旧问题", timestamp: 0 }],
      conversationId: 1,
      mode: "ask",
      isStreaming: false,
      materialScope: ["MQ.docx"],
    });

    const user = userEvent.setup();
    render(<Header />);
    await user.click(screen.getByRole("button", { name: /会话列表/ }));
    await user.click(await screen.findByRole("button", { name: /删除会话 1/ }));

    expect(api.conversations.delete).toHaveBeenCalledWith(1);
    expect(useChatStore.getState().conversationId).toBe(3);
    expect(useChatStore.getState().messages).toEqual([]);
    expect(useChatStore.getState().materialScope).toEqual([]);
  });
});

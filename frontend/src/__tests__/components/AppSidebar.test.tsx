import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppSidebar } from "@/components/AppSidebar";
import { api } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";
import type { Conversation, Material } from "@/types";

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

const conversations: Conversation[] = [
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
];

const material: Material = {
  id: 7,
  filename: "stored.docx",
  original_filename: "MQ.docx",
  file_type: "docx",
  file_size: 128,
  page_count: 1,
  processing_status: "ready",
  chunk_count: 3,
  error_message: null,
  created_at: new Date().toISOString(),
};

function renderSidebar() {
  return render(
    <AppSidebar
      conversationsVersion={0}
      materials={[material]}
      materialsLoading={false}
      uploading={false}
      onUpload={vi.fn()}
      onDeleteMaterial={vi.fn()}
      onConversationChange={vi.fn()}
    />,
  );
}

describe("AppSidebar", () => {
  beforeEach(() => {
    useChatStore.setState({
      messages: [],
      conversationId: 1,
      mode: "ask",
      isStreaming: false,
      materialScope: [],
    });
    vi.mocked(api.conversations.list).mockResolvedValue({
      total: conversations.length,
      conversations,
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
    vi.mocked(api.conversations.delete).mockResolvedValue({});
    vi.mocked(api.conversations.create).mockResolvedValue({
      id: 3,
      title: "新的复习会话",
      summary: null,
      message_count: 0,
      last_message_at: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  });

  it("renders conversations and the document library", async () => {
    renderSidebar();

    expect(await screen.findByText("新的复习会话")).toBeInTheDocument();
    expect(screen.getByText("文档库")).toBeInTheDocument();
    expect(screen.getByText("MQ.docx")).toBeInTheDocument();
  });

  it("switches to a selected conversation", async () => {
    const user = userEvent.setup();
    renderSidebar();

    await user.click(await screen.findByRole("button", { name: "会话 2" }));

    expect(useChatStore.getState().conversationId).toBe(2);
    expect(useChatStore.getState().messages[0].content).toBe("历史问题");
    expect(useChatStore.getState().materialScope).toEqual(["MQ.docx"]);
  });

  it("selects a document for material scope", async () => {
    const user = userEvent.setup();
    renderSidebar();

    await user.click(screen.getByRole("button", { name: "MQ.docx" }));

    expect(useChatStore.getState().materialScope).toEqual(["MQ.docx"]);
  });

  it("deletes a conversation from the sidebar", async () => {
    const user = userEvent.setup();
    renderSidebar();

    await user.click(await screen.findByRole("button", { name: /删除会话 1/ }));

    expect(api.conversations.delete).toHaveBeenCalledWith(1);
  });
});

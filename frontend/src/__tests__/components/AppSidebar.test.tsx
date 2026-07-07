import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

const redisMaterial: Material = {
  ...material,
  id: 8,
  filename: "stored-redis.docx",
  original_filename: "Redis.docx",
};

const processingMaterial: Material = {
  ...material,
  id: 9,
  filename: "stored-processing.docx",
  original_filename: "Draft.docx",
  processing_status: "processing",
};

function renderSidebar(
  props?: Partial<React.ComponentProps<typeof AppSidebar>>,
) {
  return render(
    <AppSidebar
      conversationsVersion={0}
      materials={[material]}
      materialsLoading={false}
      uploading={false}
      onUpload={vi.fn()}
      onDeleteMaterial={vi.fn()}
      onConversationChange={vi.fn()}
      {...props}
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
        {
          id: 11,
          conversation_id: 2,
          role: "assistant",
          content: "这是回答",
          material_scope: ["MQ.docx"],
          metadata: {
            citations: [{ source: "MQ.docx", page: 3 }],
          },
          created_at: new Date(2).toISOString(),
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

  it("keeps the full conversation title available when the visible label is clamped", async () => {
    const longTitle = "马上要面试了，给我出一道最可能考到的数据库事务题";
    vi.mocked(api.conversations.list).mockResolvedValue({
      total: 1,
      conversations: [{ ...conversations[0], title: longTitle }],
    });

    renderSidebar();

    const title = await screen.findByText(longTitle);
    expect(title).toHaveClass("conversation-title");
    expect(title).toHaveAttribute("title", longTitle);
  });

  it("switches to a selected conversation", async () => {
    const user = userEvent.setup();
    renderSidebar();

    await user.click(await screen.findByRole("button", { name: "会话 2" }));

    expect(useChatStore.getState().conversationId).toBe(2);
    expect(useChatStore.getState().messages[0].content).toBe("历史问题");
    expect(useChatStore.getState().messages[1].citations).toEqual([
      { source: "MQ.docx", page: 3, chunk_id: undefined },
    ]);
    expect(useChatStore.getState().materialScope).toEqual(["MQ.docx"]);
  });

  it("selects a document for material scope", async () => {
    const user = userEvent.setup();
    renderSidebar({ materials: [material, redisMaterial] });

    await user.click(screen.getByRole("button", { name: "MQ.docx" }));

    expect(useChatStore.getState().materialScope).toEqual(["MQ.docx"]);
  });

  it("auto-selects the only ready material when no scope is selected", async () => {
    renderSidebar();

    await waitFor(() => {
      expect(useChatStore.getState().materialScope).toEqual(["MQ.docx"]);
    });
  });

  it("does not auto-select multiple ready materials on initial load", async () => {
    renderSidebar({ materials: [material, redisMaterial] });

    await waitFor(() => {
      expect(useChatStore.getState().materialScope).toEqual([]);
    });
  });

  it("adds newly ready materials to the current scope", async () => {
    useChatStore.setState({ materialScope: ["MQ.docx"] });
    const { rerender } = renderSidebar({ materials: [material] });

    rerender(
      <AppSidebar
        conversationsVersion={0}
        materials={[material, redisMaterial]}
        materialsLoading={false}
        uploading={false}
        onUpload={vi.fn()}
        onDeleteMaterial={vi.fn()}
        onConversationChange={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(useChatStore.getState().materialScope).toEqual([
        "MQ.docx",
        "Redis.docx",
      ]);
    });
  });

  it("removes selected materials that are not ready", async () => {
    useChatStore.setState({ materialScope: ["MQ.docx", "Draft.docx"] });
    renderSidebar({ materials: [material, processingMaterial] });

    await waitFor(() => {
      expect(useChatStore.getState().materialScope).toEqual(["MQ.docx"]);
    });
  });

  it("removes a deleted material from the current scope", async () => {
    const user = userEvent.setup();
    const onDeleteMaterial = vi.fn().mockResolvedValue(undefined);
    useChatStore.setState({ materialScope: ["MQ.docx"] });
    renderSidebar({ onDeleteMaterial });

    await user.click(screen.getByRole("button", { name: "删除 MQ.docx" }));

    expect(useChatStore.getState().materialScope).toEqual([]);
    expect(onDeleteMaterial).toHaveBeenCalledWith(7);
  });

  it("clears the upload input after async upload without crashing", async () => {
    const user = userEvent.setup();
    const onUpload = vi.fn().mockResolvedValue(undefined);
    renderSidebar({ onUpload });
    const input = screen.getByLabelText("上传复习资料") as HTMLInputElement;
    const file = new File(["fake"], "MQ.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });

    await user.upload(input, file);

    expect(onUpload).toHaveBeenCalled();
    expect(input.value).toBe("");
  });

  it("uses the upload spinner class while uploading", () => {
    renderSidebar({ uploading: true });

    const uploadButton = screen.getByRole("button", { name: "上传资料" });
    const spinner = uploadButton.querySelector("svg");
    expect(spinner).toHaveClass("upload-spinner");
  });

  it("deletes a conversation from the sidebar", async () => {
    const user = userEvent.setup();
    renderSidebar();

    await user.click(await screen.findByRole("button", { name: /删除会话 1/ }));

    expect(api.conversations.delete).toHaveBeenCalledWith(1);
  });
});

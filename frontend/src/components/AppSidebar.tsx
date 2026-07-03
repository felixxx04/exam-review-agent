"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";
import type { Conversation, ConversationMessage, Material, Message } from "@/types";
import {
  AlertCircle,
  FileText,
  History,
  Loader2,
  Plus,
  Trash2,
  Upload,
  X,
} from "lucide-react";

interface AppSidebarProps {
  conversationsVersion: number;
  materials: Material[];
  materialsLoading: boolean;
  uploading: boolean;
  onUpload: (files: FileList | null) => Promise<void>;
  onDeleteMaterial: (id: number) => Promise<void>;
  onConversationChange: () => void;
}

const statusIcon: Record<Material["processing_status"], React.ReactNode> = {
  pending: <Loader2 size={14} className="animate-spin" />,
  processing: <Loader2 size={14} className="animate-spin" />,
  ready: null,
  failed: <AlertCircle size={14} />,
};

const statusLabel: Record<Material["processing_status"], string> = {
  pending: "等待处理",
  processing: "处理中",
  ready: "可使用",
  failed: "处理失败",
};

export function AppSidebar({
  conversationsVersion,
  materials,
  materialsLoading,
  uploading,
  onUpload,
  onDeleteMaterial,
  onConversationChange,
}: AppSidebarProps) {
  const {
    conversationId,
    isStreaming,
    materialScope,
    setConversationId,
    setMaterialScope,
    setMessages,
    setMode,
    startNewConversation,
  } = useChatStore();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const loadConversations = useCallback(async () => {
    setLoadingConversations(true);
    try {
      const data = await api.conversations.list();
      setConversations(data.conversations);
    } finally {
      setLoadingConversations(false);
    }
  }, []);

  useEffect(() => {
    loadConversations().catch(() => undefined);
  }, [loadConversations, conversationsVersion]);

  async function handleNewConversation() {
    if (isStreaming) return;
    const conversation = await api.conversations.create();
    startNewConversation(conversation.id);
    onConversationChange();
  }

  async function switchConversation(id: number) {
    const history = await api.conversations.messages(id);
    const restoredMessages = history.messages.flatMap(toMessage);
    const lastScope = [...history.messages]
      .reverse()
      .find((message) => message.material_scope && message.material_scope.length > 0)
      ?.material_scope;

    setConversationId(id);
    setMessages(restoredMessages);
    setMaterialScope(lastScope ?? []);
    setMode("ask");
  }

  async function deleteConversation(id: number) {
    await api.conversations.delete(id);
    const data = await api.conversations.list();
    setConversations(data.conversations);
    onConversationChange();

    if (id !== conversationId) return;
    const fallback = data.conversations[0];
    if (fallback) {
      await switchConversation(fallback.id);
      return;
    }

    const created = await api.conversations.create();
    startNewConversation(created.id);
    onConversationChange();
  }

  function toggleScope(filename: string) {
    if (materialScope.includes(filename)) {
      setMaterialScope(materialScope.filter((item) => item !== filename));
      return;
    }
    setMaterialScope([...materialScope, filename]);
  }

  return (
    <aside className="app-sidebar">
      <section className="sidebar-section">
        <div className="sidebar-section-title">
          <History size={15} />
          <span>会话列表</span>
        </div>
        <button
          type="button"
          className="sidebar-new-button"
          onClick={handleNewConversation}
          disabled={isStreaming}
        >
          <Plus size={15} />
          新建复习会话
        </button>
        <div className="sidebar-list">
          {loadingConversations && conversations.length === 0 && (
            <div className="sidebar-empty">正在加载会话</div>
          )}
          {!loadingConversations && conversations.length === 0 && (
            <div className="sidebar-empty">还没有历史会话</div>
          )}
          {conversations.map((conversation) => {
            const active = conversation.id === conversationId;
            return (
              <div
                className="sidebar-row"
                data-active={active}
                key={conversation.id}
              >
                <button
                  type="button"
                  aria-label={`会话 ${conversation.id}`}
                  className="sidebar-row-main"
                  onClick={() => switchConversation(conversation.id)}
                >
                  <span className="truncate font-medium">{conversation.title}</span>
                  <span className="text-xs text-[color:var(--color-muted)]">
                    {conversation.message_count} 条消息
                  </span>
                </button>
                <button
                  type="button"
                  aria-label={`删除会话 ${conversation.id}`}
                  className="sidebar-icon-button"
                  onClick={() => deleteConversation(conversation.id)}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            );
          })}
        </div>
      </section>

      <section className="sidebar-section">
        <div className="sidebar-section-title">
          <FileText size={15} />
          <span>文档库</span>
        </div>
        <button
          type="button"
          className="sidebar-upload-button"
          onClick={() => !uploading && inputRef.current?.click()}
          disabled={uploading}
        >
          {uploading ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
          上传资料
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.pptx"
          className="hidden"
          onChange={async (event) => {
            await onUpload(event.target.files);
            event.currentTarget.value = "";
          }}
          aria-label="上传复习资料"
        />
        <div className="sidebar-list">
          {materialsLoading && materials.length === 0 && (
            <div className="sidebar-empty">正在加载文档</div>
          )}
          {!materialsLoading && materials.length === 0 && (
            <div className="sidebar-empty">上传资料后会显示在这里</div>
          )}
          {materials.map((material) => {
            const selected = materialScope.includes(material.original_filename);
            return (
              <div
                className="material-row"
                data-active={selected}
                data-status={material.processing_status}
                key={material.id}
              >
                <button
                  type="button"
                  className="material-row-main"
                  onClick={() => toggleScope(material.original_filename)}
                >
                  <FileText size={15} />
                  <span className="min-w-0 flex-1 truncate">
                    {material.original_filename}
                  </span>
                  <span className="material-status" title={statusLabel[material.processing_status]}>
                    {statusIcon[material.processing_status]}
                  </span>
                </button>
                <button
                  type="button"
                  aria-label={`删除 ${material.original_filename}`}
                  className="sidebar-icon-button"
                  onClick={() => onDeleteMaterial(material.id)}
                >
                  <X size={14} />
                </button>
              </div>
            );
          })}
        </div>
      </section>
    </aside>
  );
}

function toMessage(message: ConversationMessage): Message[] {
  if (message.role !== "user" && message.role !== "assistant") {
    return [];
  }

  return [
    {
      id: String(message.id),
      role: message.role,
      content: message.content,
      timestamp: new Date(message.created_at).getTime(),
    },
  ];
}

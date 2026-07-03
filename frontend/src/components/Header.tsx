"use client";

import { useState } from "react";
import { useChatStore } from "@/stores/chatStore";
import { api } from "@/lib/api";
import { BookOpen, MessageCircle, BarChart3, Plus, History, Trash2 } from "lucide-react";
import type { AppMode, Conversation, ConversationMessage, Message } from "@/types";

const modes: { key: AppMode; label: string; icon: React.ReactNode }[] = [
  { key: "ask", label: "问答", icon: <MessageCircle size={16} /> },
  { key: "quiz", label: "测验", icon: <BookOpen size={16} /> },
  { key: "review", label: "复习", icon: <BarChart3 size={16} /> },
];

export function Header() {
  const {
    mode,
    conversationId,
    isStreaming,
    setConversationId,
    setMessages,
    setMaterialScope,
    setMode,
    startNewConversation,
  } = useChatStore();
  const [showConversations, setShowConversations] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);

  async function handleNewConversation() {
    if (isStreaming) return;
    const conversation = await api.conversations.create();
    startNewConversation(conversation.id);
    setShowConversations(false);
    await loadConversations();
  }

  async function loadConversations() {
    const data = await api.conversations.list();
    setConversations(data.conversations);
  }

  async function toggleConversationList() {
    if (!showConversations) {
      await loadConversations();
    }
    setShowConversations(!showConversations);
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
    setShowConversations(false);
  }

  async function deleteConversation(id: number) {
    await api.conversations.delete(id);
    const data = await api.conversations.list();
    setConversations(data.conversations);

    if (id !== conversationId) return;
    const fallback = data.conversations[0];
    if (fallback) {
      await switchConversation(fallback.id);
      return;
    }

    const created = await api.conversations.create();
    startNewConversation(created.id);
    setShowConversations(false);
  }

  return (
    <header
      className="border-b sticky top-0 z-10"
      style={{
        borderColor: "var(--color-border)",
        background: "var(--color-bg)",
        height: "var(--header-h)",
      }}
    >
      <div
        className="mx-auto flex items-center justify-between h-full px-4 sm:px-5"
        style={{ maxWidth: "var(--content-max)" }}
      >
        <h1
          className="text-base sm:text-lg font-semibold select-none shrink-0"
          style={{
            fontFamily: "var(--font-prose)",
            color: "var(--color-primary)",
            letterSpacing: "var(--tracking-tight)",
          }}
        >
          Exam Review
        </h1>

        <div className="relative flex items-center gap-1 sm:gap-2">
          <button
            type="button"
            onClick={toggleConversationList}
            disabled={isStreaming}
            className="flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50"
            style={{
              borderRadius: "var(--radius-md)",
              background: showConversations
                ? "var(--color-primary-subtle)"
                : "var(--color-surface)",
              color: showConversations
                ? "var(--color-primary)"
                : "var(--color-ink)",
              border: "1px solid var(--color-border)",
              cursor: isStreaming ? "not-allowed" : "pointer",
            }}
          >
            <History size={16} />
            会话列表
          </button>

          <button
            type="button"
            onClick={handleNewConversation}
            disabled={isStreaming}
            className="flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50"
            style={{
              borderRadius: "var(--radius-md)",
              background: "var(--color-surface)",
              color: "var(--color-ink)",
              border: "1px solid var(--color-border)",
              cursor: isStreaming ? "not-allowed" : "pointer",
            }}
          >
            <Plus size={16} />
            新会话
          </button>

          {showConversations && (
            <div
              className="absolute right-0 top-full mt-2 w-80 max-w-[calc(100vw-2rem)] p-2 shadow-lg"
              style={{
                zIndex: 30,
                borderRadius: "var(--radius-lg)",
                background: "var(--color-bg)",
                border: "1px solid var(--color-border)",
              }}
            >
              {conversations.length === 0 ? (
                <div
                  className="px-3 py-2 text-sm"
                  style={{ color: "var(--color-muted)" }}
                >
                  还没有历史会话
                </div>
              ) : (
                <div className="max-h-80 overflow-y-auto space-y-1">
                  {conversations.map((conversation) => {
                    const active = conversation.id === conversationId;
                    return (
                      <div
                        key={conversation.id}
                        className="flex items-center gap-1"
                        style={{
                          borderRadius: "var(--radius-md)",
                          background: active
                            ? "var(--color-primary-subtle)"
                            : "transparent",
                        }}
                      >
                        <button
                          type="button"
                          aria-label={`会话 ${conversation.id}`}
                          onClick={() => switchConversation(conversation.id)}
                          className="flex-1 min-w-0 text-left px-3 py-2 text-sm"
                          style={{
                            color: active
                              ? "var(--color-primary)"
                              : "var(--color-ink)",
                            background: "transparent",
                            border: "none",
                            cursor: "pointer",
                          }}
                        >
                          <div className="truncate font-medium">
                            {conversation.title}
                          </div>
                          <div
                            className="text-xs"
                            style={{ color: "var(--color-muted)" }}
                          >
                            {conversation.message_count} 条消息
                          </div>
                        </button>
                        <button
                          type="button"
                          aria-label={`删除会话 ${conversation.id}`}
                          onClick={() => deleteConversation(conversation.id)}
                          className="p-2 mr-1"
                          style={{
                            borderRadius: "var(--radius-sm)",
                            color: "var(--color-muted)",
                            background: "transparent",
                            border: "none",
                            cursor: "pointer",
                          }}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          <nav
            className="flex gap-0.5 sm:gap-1"
            role="tablist"
            aria-label="功能模式切换"
          >
            {modes.map((m, i) => {
              const active = mode === m.key;
              return (
                <button
                  key={m.key}
                  role="tab"
                  aria-selected={active}
                  tabIndex={active ? 0 : -1}
                  onClick={() => setMode(m.key)}
                  onKeyDown={(e) => {
                    const dirs: Record<string, number> = {
                      ArrowRight: 1,
                      ArrowLeft: -1,
                    };
                    if (dirs[e.key] !== undefined) {
                      e.preventDefault();
                      const next = (i + dirs[e.key] + modes.length) % modes.length;
                      setMode(modes[next].key);
                    }
                  }}
                  className="flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1.5 text-sm font-medium transition-colors"
                  style={{
                    borderRadius: "var(--radius-md)",
                    background: active ? "var(--color-primary)" : "transparent",
                    color: active ? "oklch(1 0 0)" : "var(--color-muted)",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = "var(--color-surface)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = "transparent";
                    }
                  }}
                >
                  {m.icon}
                  {m.label}
                </button>
              );
            })}
          </nav>
        </div>
      </div>
    </header>
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

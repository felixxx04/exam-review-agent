"use client";

import { useEffect } from "react";
import { useChatStore } from "@/stores/chatStore";
import { api } from "@/lib/api";
import { Header } from "@/components/Header";
import { MaterialsBar } from "@/components/MaterialsBar";
import { MessageList } from "@/components/MessageList";
import { ChatInput } from "@/components/ChatInput";
import { QuizCard } from "@/components/QuizCard";
import { DashboardCard } from "@/components/DashboardCard";

export default function Home() {
  const { mode, setConversationId, setMessages } = useChatStore();

  useEffect(() => {
    let cancelled = false;

    async function loadConversation() {
      const conversation = await api.conversations.active();
      const history = await api.conversations.messages(conversation.id);
      if (cancelled) return;

      setConversationId(conversation.id);
      setMessages(
        history.messages.flatMap((message) => {
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
        }),
      );
    }

    loadConversation().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [setConversationId, setMessages]);

  return (
    <div className="flex flex-col h-screen max-h-screen">
      <Header />
      <MaterialsBar />
      {mode === "ask" && (
        <>
          <MessageList />
          <ChatInput />
        </>
      )}
      {mode === "quiz" && <QuizCard />}
      {mode === "review" && <DashboardCard />}
    </div>
  );
}

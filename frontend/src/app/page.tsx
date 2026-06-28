"use client";

import { useChatStore } from "@/stores/chatStore";
import { Header } from "@/components/Header";
import { MaterialsBar } from "@/components/MaterialsBar";
import { MessageList } from "@/components/MessageList";
import { ChatInput } from "@/components/ChatInput";
import { QuizCard } from "@/components/QuizCard";
import { DashboardCard } from "@/components/DashboardCard";

export default function Home() {
  const { mode } = useChatStore();

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

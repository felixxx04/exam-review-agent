"use client";

import { Header } from "@/components/Header";
import { MaterialsBar } from "@/components/MaterialsBar";
import { MessageList } from "@/components/MessageList";
import { ChatInput } from "@/components/ChatInput";

export default function Home() {
  return (
    <div className="flex flex-col h-screen max-h-screen">
      <Header />
      <MaterialsBar />
      <MessageList />
      <ChatInput />
    </div>
  );
}

import { create } from "zustand";
import type { AppMode, Message } from "@/types";

interface ChatState {
  messages: Message[];
  conversationId: number | null;
  mode: AppMode;
  isStreaming: boolean;
  materialScope: string[];
  addMessage: (msg: Message) => void;
  setMessages: (messages: Message[]) => void;
  setConversationId: (id: number | null) => void;
  setMode: (mode: AppMode) => void;
  setStreaming: (v: boolean) => void;
  setMaterialScope: (scope: string[]) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  conversationId: null,
  mode: "ask",
  isStreaming: false,
  materialScope: [],
  addMessage: (msg) =>
    set((s) => {
      const existingIndex = s.messages.findIndex((item) => item.id === msg.id);
      if (existingIndex === -1) {
        return { messages: [...s.messages, msg] };
      }

      const messages = [...s.messages];
      messages[existingIndex] = msg;
      return { messages };
    }),
  setMessages: (messages) => set({ messages }),
  setConversationId: (id) => set({ conversationId: id }),
  setMode: (mode) => set({ mode }),
  setStreaming: (v) => set({ isStreaming: v }),
  setMaterialScope: (scope) => set({ materialScope: scope }),
  clearMessages: () => set({ messages: [] }),
}));

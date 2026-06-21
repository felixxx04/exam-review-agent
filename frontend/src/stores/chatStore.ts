import { create } from "zustand";
import type { AppMode, Message } from "@/types";

interface ChatState {
  messages: Message[];
  mode: AppMode;
  isStreaming: boolean;
  materialScope: string[];
  addMessage: (msg: Message) => void;
  setMode: (mode: AppMode) => void;
  setStreaming: (v: boolean) => void;
  setMaterialScope: (scope: string[]) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  mode: "ask",
  isStreaming: false,
  materialScope: [],
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setMode: (mode) => set({ mode }),
  setStreaming: (v) => set({ isStreaming: v }),
  setMaterialScope: (scope) => set({ materialScope: scope }),
  clearMessages: () => set({ messages: [] }),
}));

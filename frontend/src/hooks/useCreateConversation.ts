import { useCallback } from "react";
import { api } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";

export function useCreateConversation(onConversationChange?: () => void) {
  const { isStreaming, startNewConversation } = useChatStore();

  return useCallback(async () => {
    if (isStreaming) return;

    const conversation = await api.conversations.create();
    startNewConversation(conversation.id);
    onConversationChange?.();
  }, [isStreaming, onConversationChange, startNewConversation]);
}

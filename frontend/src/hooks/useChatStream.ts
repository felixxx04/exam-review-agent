import { useCallback, useRef } from "react";
import {
  fetchEventSource,
  EventStreamContentType,
} from "@microsoft/fetch-event-source";
import { API_BASE } from "@/lib/config";
import { useChatStore } from "@/stores/chatStore";
import { useQuizStore } from "@/stores/quizStore";
import type { Message } from "@/types";

interface UseChatStreamOptions {
  onConversationChange?: () => void;
}

export function useChatStream({
  onConversationChange,
}: UseChatStreamOptions = {}) {
  const {
    addMessage,
    conversationId,
    setConversationId,
    setStreaming,
    materialScope,
    setMode,
  } = useChatStore();
  const { setQuestions } = useQuizStore();
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (content: string) => {
      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        timestamp: Date.now(),
      };
      addMessage(userMsg);

      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",
        timestamp: Date.now(),
      };
      addMessage(assistantMsg);
      let hasReceivedToken = false;
      let hasConversationEvent = false;

      setStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        await fetchEventSource(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: content,
            conversation_id: conversationId ?? undefined,
            material_scope:
              materialScope.length > 0 ? materialScope : undefined,
          }),
          signal: controller.signal,
          async onopen(response) {
            if (
              response.ok &&
              response.headers
                .get("content-type")
                ?.includes(EventStreamContentType)
            ) {
              return;
            }
            throw new Error("Failed to connect");
          },
          onmessage(ev) {
            try {
              const data = JSON.parse(ev.data);
              if (data.event === "conversation") {
                hasConversationEvent = true;
                setConversationId(data.data.id);
              } else if (data.event === "token") {
                if (!hasReceivedToken) {
                  assistantMsg.content = "";
                  hasReceivedToken = true;
                }
                assistantMsg.content += data.data;
                addMessage({ ...assistantMsg });
              } else if (data.event === "done") {
                assistantMsg.content = data.data || assistantMsg.content;
                assistantMsg.citations =
                  data.citations || assistantMsg.citations;
                addMessage({ ...assistantMsg });
                if (data.quiz?.questions?.length) {
                  setQuestions(data.quiz.questions, data.quiz.topic || "");
                  setMode("quiz");
                }
              }
            } catch {
              // ignore parse errors
            }
          },
          onerror(err) {
            throw err;
          },
        });
      } catch {
        assistantMsg.content = controller.signal.aborted
          ? "已停止生成。"
          : "请求失败，请稍后再试。";
        addMessage({ ...assistantMsg });
      } finally {
        setStreaming(false);
        if (hasConversationEvent) {
          onConversationChange?.();
        }
      }
    },
    [
      addMessage,
      conversationId,
      setConversationId,
      setStreaming,
      materialScope,
      setMode,
      setQuestions,
      onConversationChange,
    ],
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { sendMessage, abort };
}

import { useCallback, useRef } from "react";
import {
  fetchEventSource,
  EventStreamContentType,
} from "@microsoft/fetch-event-source";
import { useChatStore } from "@/stores/chatStore";
import { useQuizStore } from "@/stores/quizStore";
import type { Message } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function useChatStream() {
  const { addMessage, setStreaming, materialScope, setMode } = useChatStore();
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

      setStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        await fetchEventSource(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: content,
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
              if (data.event === "token") {
                assistantMsg.content += data.data;
                addMessage({ ...assistantMsg });
              } else if (data.event === "done") {
                assistantMsg.content = data.data || assistantMsg.content;
                assistantMsg.citations = data.citations || assistantMsg.citations;
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
            setStreaming(false);
            throw err;
          },
        });
      } catch {
        // aborted or network error
      } finally {
        setStreaming(false);
      }
    },
    [addMessage, setStreaming, materialScope, setMode, setQuestions]
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { sendMessage, abort };
}

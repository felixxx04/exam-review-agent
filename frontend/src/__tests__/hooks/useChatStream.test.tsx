import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchEventSource,
  type EventSourceMessage,
} from "@microsoft/fetch-event-source";
import { useChatStream } from "@/hooks/useChatStream";
import { useChatStore } from "@/stores/chatStore";

vi.mock("@microsoft/fetch-event-source", () => ({
  EventStreamContentType: "text/event-stream",
  fetchEventSource: vi.fn(),
}));

describe("useChatStream", () => {
  beforeEach(() => {
    useChatStore.setState({
      messages: [],
      conversationId: null,
      mode: "ask",
      isStreaming: false,
      materialScope: [],
    });
    vi.mocked(fetchEventSource).mockReset();
    vi.stubGlobal("crypto", {
      randomUUID: vi
        .fn()
        .mockReturnValueOnce("user-message-id")
        .mockReturnValueOnce("assistant-message-id"),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("notifies when a conversation stream has completed", async () => {
    const onConversationChange = vi.fn();
    vi.mocked(fetchEventSource).mockImplementation(async (_url, options) => {
      await options.onopen?.(
        new Response(null, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
      );
      options.onmessage?.({
        data: JSON.stringify({ event: "conversation", data: { id: 12 } }),
      } as EventSourceMessage);
      options.onmessage?.({
        data: JSON.stringify({ event: "done", data: "回答完成" }),
      } as EventSourceMessage);
    });

    const { result } = renderHook(() =>
      useChatStream({ onConversationChange }),
    );

    await act(async () => {
      await result.current.sendMessage("请总结 MQ.docx 的考试重点");
    });

    expect(useChatStore.getState().conversationId).toBe(12);
    expect(onConversationChange).toHaveBeenCalledOnce();
  });
});

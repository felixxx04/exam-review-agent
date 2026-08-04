import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchEventSource,
  type EventSourceMessage,
} from "@microsoft/fetch-event-source";
import { useChatStream } from "@/hooks/useChatStream";
import { refreshSession } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";

vi.mock("@microsoft/fetch-event-source", () => ({
  EventStreamContentType: "text/event-stream",
  fetchEventSource: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getCsrfToken: vi.fn(() => "csrf-token"),
  refreshSession: vi.fn(),
  signalAuthRequired: vi.fn(),
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
    vi.mocked(refreshSession).mockReset();
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

    const options = vi.mocked(fetchEventSource).mock.calls[0][1];
    expect(options.credentials).toBe("include");
    expect(options.headers).toEqual(
      expect.objectContaining({ "X-CSRF-Token": expect.any(String) }),
    );
    expect(useChatStore.getState().conversationId).toBe(12);
    expect(onConversationChange).toHaveBeenCalledOnce();
  });

  it("refreshes an expired session and reconnects the stream once", async () => {
    vi.mocked(refreshSession).mockResolvedValue({} as never);
    vi.mocked(fetchEventSource)
      .mockImplementationOnce(async (_url, options) => {
        await options.onopen?.(new Response(null, { status: 401 }));
      })
      .mockImplementationOnce(async (_url, options) => {
        await options.onopen?.(
          new Response(null, {
            status: 200,
            headers: { "content-type": "text/event-stream" },
          }),
        );
        options.onmessage?.({
          data: JSON.stringify({ event: "done", data: "恢复成功" }),
        } as EventSourceMessage);
      });

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.sendMessage("继续回答");
    });

    expect(refreshSession).toHaveBeenCalledOnce();
    expect(fetchEventSource).toHaveBeenCalledTimes(2);
    expect(useChatStore.getState().messages.at(-1)?.content).toBe("恢复成功");
  });
});

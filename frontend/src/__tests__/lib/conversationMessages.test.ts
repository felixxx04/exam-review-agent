import { describe, expect, it } from "vitest";
import { conversationMessageToMessages } from "@/lib/conversationMessages";
import type { ConversationMessage } from "@/types";

function baseMessage(
  overrides: Partial<ConversationMessage> = {},
): ConversationMessage {
  return {
    id: 12,
    conversation_id: 2,
    role: "assistant",
    content: "这是回答",
    material_scope: ["MQ.docx"],
    metadata: {},
    created_at: new Date(1000).toISOString(),
    ...overrides,
  };
}

describe("conversationMessageToMessages", () => {
  it("converts user and assistant conversation messages into chat messages", () => {
    const messages = conversationMessageToMessages(
      baseMessage({
        metadata: {
          citations: [{ source: "MQ.docx", page: 3, chunk_id: "chunk-1" }],
        },
      }),
    );

    expect(messages).toEqual([
      {
        id: "12",
        role: "assistant",
        content: "这是回答",
        citations: [{ source: "MQ.docx", page: 3, chunk_id: "chunk-1" }],
        timestamp: new Date(1000).getTime(),
      },
    ]);
  });

  it("filters unsupported roles and malformed citations", () => {
    expect(
      conversationMessageToMessages(baseMessage({ role: "system" })),
    ).toEqual([]);

    expect(
      conversationMessageToMessages(
        baseMessage({
          metadata: {
            citations: [{ page: 1 }, null, { source: "Valid.pdf" }],
          },
        }),
      )[0].citations,
    ).toEqual([{ source: "Valid.pdf", page: undefined, chunk_id: undefined }]);
  });
});

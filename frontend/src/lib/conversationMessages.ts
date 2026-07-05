import type { ConversationMessage, Message } from "@/types";

export function conversationMessageToMessages(
  message: ConversationMessage,
): Message[] {
  if (message.role !== "user" && message.role !== "assistant") {
    return [];
  }

  const citations = Array.isArray(message.metadata?.citations)
    ? message.metadata.citations
        .filter(
          (
            citation,
          ): citation is { source: string; page?: number; chunk_id?: string } =>
            typeof citation === "object" &&
            citation !== null &&
            typeof citation.source === "string",
        )
        .map((citation) => ({
          source: citation.source,
          page: typeof citation.page === "number" ? citation.page : undefined,
          chunk_id:
            typeof citation.chunk_id === "string"
              ? citation.chunk_id
              : undefined,
        }))
    : undefined;

  return [
    {
      id: String(message.id),
      role: message.role,
      content: message.content,
      citations: citations && citations.length > 0 ? citations : undefined,
      timestamp: new Date(message.created_at).getTime(),
    },
  ];
}

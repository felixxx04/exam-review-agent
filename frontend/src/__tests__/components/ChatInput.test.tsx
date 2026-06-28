import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatInput } from "@/components/ChatInput";
import { useChatStore } from "@/stores/chatStore";

vi.mock("@/hooks/useChatStream", () => ({
  useChatStream: () => ({
    sendMessage: vi.fn(),
    abort: vi.fn(),
  }),
}));

describe("ChatInput", () => {
  beforeEach(() => {
    useChatStore.setState({
      messages: [],
      mode: "ask",
      isStreaming: false,
      materialScope: [],
    });
  });

  it("renders text input and send button", () => {
    render(<ChatInput />);
    expect(screen.getByPlaceholderText(/输入你的问题/)).toBeInTheDocument();
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("send button is disabled when input is empty", () => {
    render(<ChatInput />);
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
  });

  it("can type in the input", async () => {
    const user = userEvent.setup();
    render(<ChatInput />);
    const input = screen.getByPlaceholderText(/输入你的问题/);
    await user.type(input, "test question");
    expect(input).toHaveValue("test question");
  });

  it("shows stop button when streaming", () => {
    useChatStore.setState({ isStreaming: true });
    render(<ChatInput />);
    expect(screen.getByPlaceholderText(/等待回复/)).toBeInTheDocument();
  });
});

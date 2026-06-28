import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Header } from "@/components/Header";
import { useChatStore } from "@/stores/chatStore";

describe("Header", () => {
  beforeEach(() => {
    useChatStore.setState({
      messages: [],
      mode: "ask",
      isStreaming: false,
      materialScope: [],
    });
  });

  it("renders three mode buttons", () => {
    render(<Header />);
    expect(screen.getByRole("tab", { name: /问答/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /测验/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /复习/ })).toBeInTheDocument();
  });

  it("renders the app title", () => {
    render(<Header />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Exam Review");
  });

  it("ask tab is selected by default", () => {
    render(<Header />);
    expect(screen.getByRole("tab", { name: /问答/ })).toHaveAttribute("aria-selected", "true");
  });

  it("clicking quiz tab changes mode", async () => {
    const user = userEvent.setup();
    render(<Header />);
    await user.click(screen.getByRole("tab", { name: /测验/ }));
    expect(useChatStore.getState().mode).toBe("quiz");
  });

  it("clicking review tab changes mode", async () => {
    const user = userEvent.setup();
    render(<Header />);
    await user.click(screen.getByRole("tab", { name: /复习/ }));
    expect(useChatStore.getState().mode).toBe("review");
  });
});

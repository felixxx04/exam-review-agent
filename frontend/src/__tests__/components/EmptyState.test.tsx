import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { BookOpen } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";

describe("EmptyState", () => {
  it("renders a reusable empty state with the requested heading level", () => {
    render(
      <EmptyState
        icon={<BookOpen data-testid="empty-icon" />}
        title="开始一次测验"
        description='在问答模式下输入"开始测验"来生成题目'
        headingLevel={2}
        maxWidth="360px"
      />,
    );

    expect(
      screen.getByRole("heading", { level: 2, name: "开始一次测验" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/开始测验/)).toBeInTheDocument();
    expect(screen.getByTestId("empty-icon")).toBeInTheDocument();
  });

  it("preserves configurable spacing and text scale for existing screens", () => {
    const { container } = render(
      <EmptyState
        icon={<BookOpen />}
        title="暂无薄弱知识点"
        description="完成一些测验后再来查看"
        headingLevel={3}
        padding="var(--space-10) var(--space-5)"
        iconMarginBottom="var(--space-5)"
        titleFontSize="var(--text-lg)"
        maxWidth="320px"
      />,
    );

    expect(container.firstElementChild).toHaveAttribute(
      "style",
      expect.stringContaining("padding: var(--space-10) var(--space-5)"),
    );
    expect(
      screen.getByRole("heading", { level: 3, name: "暂无薄弱知识点" }),
    ).toHaveStyle({ fontSize: "var(--text-lg)" });
    expect(screen.getByText("完成一些测验后再来查看")).toHaveStyle({
      maxWidth: "320px",
    });
  });
});

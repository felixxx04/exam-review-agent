import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { StudyPlanDialog } from "@/components/review/StudyPlanDialog";
import type { StudyPlanData } from "@/types";

const longPlan: StudyPlanData = {
  message: "已生成复习计划",
  plan: Array.from({ length: 10 }, (_, index) => ({
    day: index + 1,
    topics: [`第 ${index + 1} 天知识点`],
    tasks: [
      `完成第 ${index + 1} 天错题复盘。`,
      `整理第 ${index + 1} 天订正笔记。`,
    ],
  })),
};

describe("StudyPlanDialog", () => {
  it("keeps long study plans scrollable inside the dialog", () => {
    render(
      <StudyPlanDialog
        open
        loading={false}
        plan={longPlan}
        onClose={vi.fn()}
        onGenerate={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("dialog", { name: "生成复习计划" }),
    ).toBeInTheDocument();
    const panel = document.body.querySelector(".study-plan-dialog-panel");

    expect(panel).toBeInTheDocument();
    expect(panel).toHaveStyle({
      maxHeight: "calc(100vh - 2rem)",
      overflowY: "auto",
    });
  });
});

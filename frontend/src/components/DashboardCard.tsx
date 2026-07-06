"use client";

import { ReviewWorkbench } from "@/components/review/ReviewWorkbench";
import { useChatStore } from "@/stores/chatStore";

export function DashboardCard() {
  const { mode } = useChatStore();
  if (mode !== "review") return null;
  return <ReviewWorkbench />;
}

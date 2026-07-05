import type { ReactNode } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import type { Material } from "@/types";

type MaterialStatus = Material["processing_status"];

interface MaterialStatusIconOptions {
  size?: number;
  pulseProcessing?: boolean;
}

export const materialStatusLabel: Record<MaterialStatus, string> = {
  pending: "等待处理",
  processing: "处理中",
  ready: "可使用",
  failed: "处理失败",
};

const materialStatusColor: Record<MaterialStatus, string> = {
  pending: "var(--color-muted)",
  processing: "var(--color-accent)",
  ready: "var(--color-success)",
  failed: "var(--color-error)",
};

export function getMaterialStatusColor(status: MaterialStatus) {
  return materialStatusColor[status];
}

export function getMaterialStatusIcon(
  status: MaterialStatus,
  options: MaterialStatusIconOptions = {},
): ReactNode {
  const size = options.size ?? 14;

  if (status === "ready") return null;
  if (status === "failed") return <AlertCircle size={size} />;

  const icon = <Loader2 size={size} className="animate-spin" />;
  if (status === "processing" && options.pulseProcessing) {
    return (
      <span className="processing-icon" style={{ display: "inline-flex" }}>
        {icon}
      </span>
    );
  }

  return icon;
}

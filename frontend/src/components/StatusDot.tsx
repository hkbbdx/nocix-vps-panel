import type { TaskStatus } from "../lib/types";

const labels: Record<TaskStatus, string> = {
  stopped: "Stopped",
  running: "Running",
  checking: "Checking",
  ordering: "Ordering",
  paused: "Paused",
  success: "Success",
  failed: "Failed",
  unknown: "Unknown",
  submitted_pending_confirmation: "Pending confirmation",
};

export function StatusDot({ status }: { status: TaskStatus | string }) {
  const normalized = (status in labels ? status : "stopped") as TaskStatus;
  return (
    <span className={`status status-${normalized}`}>
      <span className="status-dot" aria-hidden="true" />
      <span>{labels[normalized]}</span>
    </span>
  );
}

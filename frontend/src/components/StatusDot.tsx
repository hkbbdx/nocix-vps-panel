import type { TaskStatus } from "../lib/types";
import { useTranslation } from "../i18n";

export function StatusDot({ status }: { status: TaskStatus | string }) {
  const { t } = useTranslation();
  const labels: Record<TaskStatus, string> = {
    stopped: t("status.stopped"), running: t("status.running"), checking: t("status.checking"), ordering: t("status.ordering"), paused: t("status.paused"), success: t("status.success"), failed: t("status.failed"), unknown: t("status.unknown"), submitted_pending_confirmation: t("status.pending"), login_first: t("status.loginFirst"), login_second: t("status.loginSecond"), waiting_for_email_code: t("status.waitingForEmailCode"),
  };
  const normalized = (status in labels ? status : "stopped") as TaskStatus;
  return (
    <span className={`status status-${normalized}`}>
      <span className="status-dot" aria-hidden="true" />
      <span>{labels[normalized]}</span>
    </span>
  );
}

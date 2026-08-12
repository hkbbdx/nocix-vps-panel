import { useEffect, useRef, type RefObject } from "react";
import type { Task, TaskInput } from "../lib/types";
import { TaskForm } from "./TaskForm";

interface TaskDialogProps {
  task?: Task | null;
  onSubmit: (input: TaskInput | Partial<TaskInput>) => void | Promise<void>;
  onClose: () => void;
  busy?: boolean;
  restoreFocusRef?: RefObject<HTMLElement>;
}

export function TaskDialog({ task, onSubmit, onClose, busy = false, restoreFocusRef }: TaskDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    const focusTarget = dialog?.querySelector<HTMLElement>("input[inputmode='numeric']") ??
      dialog?.querySelector<HTMLElement>("input:not([type='checkbox']), button, select, textarea");
    focusTarget?.focus();
    const getFocusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>(
      "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
    ) ?? []);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key === "Tab" && dialog) {
        const focusable = getFocusable();
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      (restoreFocusRef?.current ?? previous)?.focus();
    };
  }, [restoreFocusRef]);

  return (
    <div
      ref={dialogRef}
      className="modal-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="task-dialog-title"
      aria-describedby="task-dialog-description"
    >
      <p id="task-dialog-description" className="sr-only">
        Configure a NOCIX product monitor and its saved account checkout settings.
      </p>
      <TaskForm task={task} busy={busy} onSubmit={onSubmit} onCancel={onClose} />
    </div>
  );
}

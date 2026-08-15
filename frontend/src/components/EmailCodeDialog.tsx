import { useEffect, useRef, useState, type FormEvent, type RefObject } from "react";
import { formatApiError } from "../lib/api";
import { useTranslation } from "../i18n";

interface EmailCodeDialogProps {
  onSubmit: (code: string) => void | Promise<void>;
  onCancel: () => void;
  busy?: boolean;
  restoreFocusRef?: RefObject<HTMLElement>;
}

const CODE_PATTERN = /^[0-9]{4,12}$/;

export function EmailCodeDialog({ onSubmit, onCancel, busy = false, restoreFocusRef }: EmailCodeDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCancelRef = useRef(onCancel);
  const codeRef = useRef("");
  const [code, setCodeState] = useState("");
  const [error, setError] = useState("");
  const { t } = useTranslation();
  onCancelRef.current = onCancel;

  const clearCode = () => {
    codeRef.current = "";
    setCodeState("");
  };

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    dialog?.querySelector<HTMLElement>("input")?.focus();
    const getFocusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>(
      "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
    ) ?? []);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        clearCode();
        setError("");
        onCancelRef.current();
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
      clearCode();
      setError("");
      (restoreFocusRef?.current ?? previous)?.focus();
    };
  }, [restoreFocusRef]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const submittedCode = codeRef.current;
    clearCode();
    setError("");
    if (!CODE_PATTERN.test(submittedCode)) {
      setError(t("login.codeValidation"));
      return;
    }
    try {
      await onSubmit(submittedCode);
    } catch (submitError) {
      setError(formatApiError(submitError, t, "login.submitFailed"));
    }
  };

  return (
    <div ref={dialogRef} className="modal-panel email-code-dialog" role="dialog" aria-modal="true" aria-labelledby="email-code-dialog-title" aria-describedby="email-code-dialog-description">
      <form className="task-form" onSubmit={(event) => void submit(event)}>
        <div className="dialog-heading">
          <div><p className="eyebrow">{t("login.eyebrow")}</p><h2 id="email-code-dialog-title">{t("login.title")}</h2></div>
          <button type="button" className="icon-button" aria-label={t("login.close")} onClick={() => { clearCode(); setError(""); onCancel(); }}>×</button>
        </div>
        <p id="email-code-dialog-description" className="panel-copy">{t("login.description")}</p>
        <label htmlFor="email-verification-code">{t("login.codeLabel")}
          <input id="email-verification-code" type="password" inputMode="numeric" autoComplete="one-time-code" maxLength={12} value={code} onChange={(event) => { codeRef.current = event.target.value; setCodeState(event.target.value); }} aria-invalid={Boolean(error)} />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="dialog-actions">
          <button type="button" className="button-secondary" disabled={busy} onClick={() => { clearCode(); setError(""); onCancel(); }}>{t("login.cancel")}</button>
          <button type="submit" className="button-primary" disabled={busy}>{busy ? t("login.submitting") : t("login.submit")}</button>
        </div>
      </form>
    </div>
  );
}

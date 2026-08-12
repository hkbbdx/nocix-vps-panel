import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, clearApiKey, formatApiError, getApiKey, logoutEvent, setApiKey, type ApiMessageKey } from "../lib/api";
import { useTranslation } from "../i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

export function AuthGate({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [key, setKey] = useState(getApiKey() ?? "");
  const [authenticated, setAuthenticated] = useState(Boolean(getApiKey()));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { t } = useTranslation();
  const translateRef = useRef(t);
  translateRef.current = t;

  useEffect(() => {
    const handleSessionEnd = (event: Event) => {
      clearApiKey();
      queryClient.getQueryCache().clear();
      setKey("");
      setAuthenticated(false);
      const messageKey = event instanceof CustomEvent ? event.detail?.messageKey as ApiMessageKey | undefined : undefined;
      setError(messageKey ? translateRef.current(messageKey) : event.type === logoutEvent ? translateRef.current("auth.loggedOut") : translateRef.current("auth.rejected"));
    };
    window.addEventListener("nocix:unauthorized", handleSessionEnd);
    window.addEventListener(logoutEvent, handleSessionEnd);
    return () => {
      window.removeEventListener("nocix:unauthorized", handleSessionEnd);
      window.removeEventListener(logoutEvent, handleSessionEnd);
    };
  }, [queryClient]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!key.trim()) return setError(t("auth.enterKey"));
    setBusy(true);
    setError("");
    setApiKey(key.trim());
    try {
      await api.stats();
      setAuthenticated(true);
    } catch (error) {
      clearApiKey();
      queryClient.getQueryCache().clear();
      setAuthenticated(false);
      setError(formatApiError(error, translateRef.current, "auth.failed"));
    } finally {
      setBusy(false);
    }
  };

  if (authenticated) return <>{children}</>;
  return (
    <main className="auth-screen">
       <section className="auth-panel" aria-labelledby="auth-title">
         <LanguageSwitcher />
         <div className="brand-lockup"><span className="brand-glyph">N</span><span>NOCIX <b>CONSOLE</b></span></div>
         <p className="eyebrow">{t("auth.eyebrow")}</p>
         <h1 id="auth-title">{t("auth.title")}</h1>
         <p className="auth-copy">{t("auth.copy")}</p>
         <form onSubmit={submit}>
           <label htmlFor="api-key">{t("auth.keyLabel")}</label>
          <input id="api-key" type="password" value={key} onChange={(event) => setKey(event.target.value)} autoComplete="off" autoFocus required />
          {error && <p className="form-error" role="alert">{error}</p>}
           <button className="button-primary full-width" type="submit" disabled={busy}>{busy ? t("auth.checking") : t("auth.enter")}</button>
         </form>
         <p className="security-note"><span className="status-dot status-dot-good" /> {t("auth.session")}</p>
      </section>
    </main>
  );
}

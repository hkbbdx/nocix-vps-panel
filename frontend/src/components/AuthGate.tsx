import { FormEvent, ReactNode, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, clearApiKey, getApiKey, setApiKey } from "../lib/api";

export function AuthGate({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [key, setKey] = useState(getApiKey() ?? "");
  const [authenticated, setAuthenticated] = useState(Boolean(getApiKey()));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const handleUnauthorized = () => {
      clearApiKey();
      queryClient.getQueryCache().clear();
      setKey("");
      setAuthenticated(false);
      setError("API key rejected. Enter a valid key to continue.");
    };
    window.addEventListener("nocix:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("nocix:unauthorized", handleUnauthorized);
  }, [queryClient]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!key.trim()) return setError("Enter an API key.");
    setBusy(true);
    setError("");
    setApiKey(key.trim());
    try {
      await api.stats();
      setAuthenticated(true);
    } catch {
      clearApiKey();
      queryClient.getQueryCache().clear();
      setAuthenticated(false);
      setError("That API key could not authenticate with the panel.");
    } finally {
      setBusy(false);
    }
  };

  if (authenticated) return <>{children}</>;
  return (
    <main className="auth-screen">
      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="brand-lockup"><span className="brand-glyph">N</span><span>NOCIX <b>CONSOLE</b></span></div>
        <p className="eyebrow">Private operations interface</p>
        <h1 id="auth-title">API key</h1>
        <p className="auth-copy">Connect to your NOCIX worker service. The key stays in this browser session only.</p>
        <form onSubmit={submit}>
          <label htmlFor="api-key">Panel API key</label>
          <input id="api-key" type="password" value={key} onChange={(event) => setKey(event.target.value)} autoComplete="off" autoFocus required />
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button-primary full-width" type="submit" disabled={busy}>{busy ? "Checking…" : "Enter console"}</button>
        </form>
        <p className="security-note"><span className="status-dot status-dot-good" /> Session-scoped authentication</p>
      </section>
    </main>
  );
}

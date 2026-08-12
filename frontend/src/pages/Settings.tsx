import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useSettings } from "../hooks/use-settings";
import { useTranslation } from "../i18n";
import { formatApiError } from "../lib/api";

export function Settings() {
  const client = useQueryClient();
  const query = useSettings();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [token, setToken] = useState("");
  const [chatId, setChatId] = useState("");
  const [notice, setNotice] = useState("");
  const [noticeError, setNoticeError] = useState(false);
  const { t } = useTranslation();
  const update = useMutation({
    mutationFn: api.settings.update,
    onSuccess: (data) => { client.setQueryData(["settings"], data); setToken(""); setChatId(""); setNoticeError(false); setNotice(t("settings.saved")); },
    onError: (error) => { setNoticeError(true); setNotice(formatApiError(error, t, "settings.saveError")); },
  });
  const test = useMutation({
    mutationFn: api.settings.testTelegram,
    onSuccess: (data) => { setNoticeError(!data.success); setNotice(data.message); },
    onError: (error) => { setNoticeError(true); setNotice(formatApiError(error, t, "settings.testFailed")); },
  });
  const settings = query.data;
  const save = () => update.mutate({ telegram_enabled: enabled ?? settings?.telegram_enabled, ...(token ? { telegram_bot_token: token } : {}), ...(chatId ? { telegram_chat_id: chatId } : {}) });
  return <div className="page-stack">
    <div className="page-heading"><div><p className="eyebrow">{t("settings.eyebrow")}</p><h1>{t("settings.title")}</h1><p className="page-subtitle">{t("settings.subtitle")}</p></div></div>
    {notice && <div className={`toast ${noticeError ? "toast-error" : ""}`} role={noticeError ? "alert" : "status"}>{notice}</div>}
    {query.isLoading ? <div className="panel loading-block">{t("settings.loading")}</div> : query.error ? <div className="panel inline-error" role="alert">{t("settings.loadError")}</div> : <div className="settings-grid">
      <section className="panel"><div className="panel-heading"><div><p className="eyebrow">{t("settings.runtime")}</p><h2>{t("settings.connections")}</h2></div></div><div className="setting-status-list"><SettingStatus label={t("settings.apiAuth")} ok={settings?.api_key_configured} /><SettingStatus label={t("settings.browser")} ok={settings?.browser_configured} /><SettingStatus label={t("settings.encryption")} ok={settings?.encryption_key_configured} /><SettingStatus label={t("settings.telegram")} ok={settings?.telegram_configured} detail={settings?.telegram_enabled ? t("settings.enabled") : t("settings.disabled")} /><SettingStatus label={t("settings.payment")} ok detail={t("settings.notUsed")} /></div></section>
      <section className="panel"><div className="panel-heading"><div><p className="eyebrow">{t("settings.notifications")}</p><h2>{t("settings.delivery")}</h2></div></div><p className="panel-copy">{t("settings.copy")}</p><label className="confirm-row"><input type="checkbox" checked={enabled ?? settings?.telegram_enabled ?? false} onChange={(event) => setEnabled(event.target.checked)} /><span><strong>{t("settings.enableTelegram")}</strong><small>{t("settings.notificationDetail")}</small></span></label><label>{t("settings.botToken")}<input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder={settings?.telegram_configured ? t("settings.replaceToken") : t("settings.pasteToken")} /></label><label>{t("settings.chatId")}<input value={chatId} onChange={(event) => setChatId(event.target.value)} placeholder={settings?.telegram_configured ? t("settings.replaceChat") : t("settings.enterChat")} /></label><div className="dialog-actions"><button className="button-secondary" onClick={() => test.mutate()} disabled={test.isPending}>{test.isPending ? t("settings.testing") : t("settings.test")}</button><button className="button-primary" onClick={save} disabled={update.isPending}>{update.isPending ? t("settings.saving") : t("settings.save")}</button></div></section>
    </div>}
  </div>;
}

function SettingStatus({ label, ok, detail }: { label: string; ok?: boolean; detail?: string }) { const { t } = useTranslation(); return <div className="setting-status"><span className={`status-dot ${ok ? "status-dot-good" : "status-dot-muted"}`} /><div><strong>{label}</strong><span>{detail ?? (ok ? t("settings.configured") : t("settings.notConfigured"))}</span></div></div>; }

import { ReactNode, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { NavLink, useNavigate } from "react-router-dom";
import { clearApiKey, logoutEvent } from "../lib/api";
import { useTranslation } from "../i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

export function Layout({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const railRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  const { t } = useTranslation();
  const navigation = [
    { to: "/", label: t("nav.overview"), icon: "◌" },
    { to: "/tasks", label: t("nav.tasks"), icon: "▦" },
    { to: "/orders", label: t("nav.orders"), icon: "↗" },
    { to: "/logs", label: t("nav.logs"), icon: "≡" },
    { to: "/settings", label: t("nav.settings"), icon: "⚙" },
  ];

  useEffect(() => {
    const media = window.matchMedia("(max-width: 680px)");
    const update = () => setIsMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const rail = railRef.current;
    if (!rail) return;
    const hidden = isMobile && !mobileOpen;
    if (hidden) rail.setAttribute("inert", "");
    else rail.removeAttribute("inert");
    if (isMobile) rail.setAttribute("aria-hidden", String(hidden));
    else rail.removeAttribute("aria-hidden");
  }, [isMobile, mobileOpen]);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && mobileOpen) {
        setMobileOpen(false);
        window.setTimeout(() => menuRef.current?.focus(), 0);
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [mobileOpen]);

  const closeMobile = () => {
    setMobileOpen(false);
    window.setTimeout(() => menuRef.current?.focus(), 0);
  };

  const signOut = () => {
    clearApiKey();
    queryClient.getQueryCache().clear();
    setMobileOpen(false);
    navigate("/", { replace: true });
    window.dispatchEvent(new Event(logoutEvent));
  };

  return (
    <div className="app-shell">
       <button className={`mobile-scrim ${mobileOpen ? "is-open" : ""}`} aria-label={t("nav.close")} onClick={closeMobile} />
      <aside ref={railRef} id="mobile-navigation" className={`sidebar ${mobileOpen ? "is-open" : ""}`}>
         <div className="sidebar-top"><div className="brand-lockup"><span className="brand-glyph">N</span><span>NOCIX <b>CONSOLE</b></span></div><button className="icon-button mobile-close" aria-label={t("nav.close")} onClick={closeMobile}>×</button></div>
         <div className="rail-label">{t("nav.controlRoom")}</div>
         <nav aria-label={t("nav.primary")} className="main-nav">
          {navigation.map((item) => <NavLink key={item.to} to={item.to} end={item.to === "/"} onClick={() => isMobile && closeMobile()}><span className="nav-icon">{item.icon}</span>{item.label}</NavLink>)}
        </nav>
         <div className="sidebar-footer"><div className="connection-panel"><span className="status-dot status-dot-good" /><div><strong>{t("nav.apiConnected")}</strong><small>{t("nav.sessionActive")}</small></div></div><button className="signout" onClick={signOut}>{t("nav.signOut")} <span>↪</span></button></div>
      </aside>
      <section className="content-shell">
         <header className="topbar"><button ref={menuRef} className="mobile-menu icon-button" aria-label={t("nav.open")} aria-expanded={mobileOpen} aria-controls="mobile-navigation" onClick={() => setMobileOpen(true)}>☰</button><div className="topbar-context"><span className="context-kicker">{t("top.context")}</span><span className="context-title">{t("top.title")}</span></div><div className="topbar-meta"><span className="live-pill"><span className="status-dot status-dot-good" /> {t("top.live")}</span><span className="topbar-date">{t("top.localSession")}</span><LanguageSwitcher /></div></header>
        <main className="page-content">{children}</main>
      </section>
    </div>
  );
}

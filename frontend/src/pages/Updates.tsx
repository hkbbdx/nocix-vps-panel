import { Link } from "react-router-dom";
import { useTranslation } from "../i18n";
import { updates, type UpdateEntry } from "../lib/updates";

export function Updates() {
  const { language, t } = useTranslation();

  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <p className="eyebrow">{t("updates.eyebrow")}</p>
          <h1>{t("updates.title")}</h1>
          <p className="page-subtitle">{t("updates.subtitle")}</p>
        </div>
        <Link className="button-secondary" to="/">{t("updates.backToOverview")}</Link>
      </div>
      <section className="updates-list" aria-label={t("updates.title")}>
        {updates.map((entry) => <UpdateCard key={entry.commit} entry={entry} language={language} t={t} />)}
      </section>
    </div>
  );
}

export function UpdateCard({ entry, language, t, compact = false }: { entry: UpdateEntry; language: "zh-CN" | "en-US"; t: (key: string) => string; compact?: boolean }) {
  const copy = entry[language === "zh-CN" ? "zh" : "en"];
  const items = compact ? copy.items.slice(0, 3) : copy.items;
  return (
    <article className={`panel update-card${compact ? " update-card-compact" : ""}`} aria-label={`${t("updates.entryLabel")} ${entry.date}`}>
      <div className="update-meta">
        <span className="sr-only">{t("updates.date")}</span>
        <time dateTime={entry.date}>{entry.date}</time>
        <span className={`update-type update-type-${entry.type}`}>{t(`updates.type.${entry.type}`)}</span>
        <code>{entry.commit}</code>
      </div>
      <h2>{copy.title}</h2>
      <ul>
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </article>
  );
}

import { useTranslation } from "../i18n";

export function LanguageSwitcher() {
  const { language, setLanguage, t } = useTranslation();
  const nextLanguage = language === "zh-CN" ? "en-US" : "zh-CN";
  return <button className="language-switcher" type="button" onClick={() => setLanguage(nextLanguage)} aria-label={`${t("language.switchTo")} / ${t("language.current")}`}><span aria-hidden="true">文</span>{t("language.switchTo")}</button>;
}

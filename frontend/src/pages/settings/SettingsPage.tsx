import { LLMSection } from "./LLMSection";
import { ProfileSection } from "./ProfileSection";
import { ResumeSection } from "./ResumeSection";
import styles from "./settings.module.css";
import { SourcesSection } from "./SourcesSection";
import { TelegramSection } from "./TelegramSection";

const SECTIONS = [
  { id: "resume", title: "Резюме" },
  { id: "profile", title: "Критерии поиска" },
  { id: "telegram", title: "Telegram" },
  { id: "sources", title: "Сбор вакансий" },
  { id: "llm", title: "Оценка" },
];

export function SettingsPage() {
  return (
    <div className={styles.page}>
      <nav className={styles.toc} aria-label="Разделы настроек">
        <h1>Настройки</h1>
        <ul>
          {SECTIONS.map((section) => (
            <li key={section.id}>
              <a href={`#${section.id}`}>{section.title}</a>
            </li>
          ))}
        </ul>
      </nav>
      <div className={styles.sections}>
        <ResumeSection />
        <ProfileSection />
        <TelegramSection />
        <SourcesSection />
        <LLMSection />
      </div>
    </div>
  );
}

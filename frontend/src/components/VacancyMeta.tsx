import type { VacancyListItem } from "../api/models";
import { formatAge, formatSalary } from "../lib/format";
import { contractLabel, workFormatLabel } from "../lib/labels";
import styles from "./VacancyMeta.module.css";

/** Компания, зарплата, формат и оформление — строкой фактов под названием. */
export function VacancyMeta({ vacancy }: { vacancy: VacancyListItem }) {
  const salary = formatSalary(vacancy);
  const facts = [
    vacancy.company,
    ...vacancy.work_formats.map(workFormatLabel),
    ...vacancy.contract_types.map(contractLabel),
  ].filter((fact): fact is string => Boolean(fact));
  return (
    <div className={styles.meta}>
      <ul className={styles.facts}>
        <li className={salary ? styles.salary : styles.noSalary}>
          {salary ?? "зарплата не указана"}
        </li>
        {facts.map((fact, index) => (
          <li key={index}>{fact}</li>
        ))}
      </ul>
      <span className={styles.origin}>
        {vacancy.source_code}
        {vacancy.published_at && `, ${formatAge(vacancy.published_at)}`}
        {!vacancy.is_active && ", снята с публикации"}
      </span>
    </div>
  );
}

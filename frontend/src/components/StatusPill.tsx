import type { ApplicationStatus } from "../api/models";
import { APPLICATION_STATUS_LABELS } from "../lib/labels";
import styles from "./StatusPill.module.css";

/** Статус отклика одним видом везде: в ленте, журнале и настройках цвет значит одно и то же. */
export function StatusPill({ status }: { status: ApplicationStatus }) {
  return (
    <span className={styles.pill} data-status={status}>
      {APPLICATION_STATUS_LABELS[status]}
    </span>
  );
}

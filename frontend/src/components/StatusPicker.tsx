import type { ApplicationStatus } from "../api/models";
import { APPLICATION_STATUSES, APPLICATION_STATUS_LABELS } from "../lib/labels";
import styles from "./StatusPicker.module.css";

interface Props {
  value: ApplicationStatus | null;
  onChange: (status: ApplicationStatus) => void;
  disabled?: boolean;
  /** Подпись группы для экранных читалок. */
  label: string;
}

/** Статус отклика: все шесть вариантов на виду, выбранный отмечен. */
export function StatusPicker({ value, onChange, disabled = false, label }: Props) {
  return (
    <div className={styles.picker} role="group" aria-label={label}>
      {APPLICATION_STATUSES.map((status) => (
        <button
          key={status}
          type="button"
          className={styles.option}
          aria-pressed={status === value}
          disabled={disabled}
          onClick={() => {
            if (status !== value) onChange(status);
          }}
        >
          {APPLICATION_STATUS_LABELS[status]}
        </button>
      ))}
    </div>
  );
}

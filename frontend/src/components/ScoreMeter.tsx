import type { Evaluation } from "../api/models";
import { VERDICT_LABELS } from "../lib/labels";
import styles from "./ScoreMeter.module.css";

const SEGMENTS = 10;

interface Props {
  evaluation: Evaluation | null | undefined;
  size?: "row" | "large";
}

/**
 * Балл оценки: цифра и «шкала сигнала» из 10 делений в цвете вердикта.
 * Главный элемент интерфейса — по нему решается, открывать ли вакансию.
 */
export function ScoreMeter({ evaluation, size = "row" }: Props) {
  const className = `${styles.meter} ${styles[size]}`;
  if (!evaluation || evaluation.status !== "done" || evaluation.score === null) {
    const label =
      evaluation?.status === "pending"
        ? "Идёт оценка"
        : evaluation?.status === "failed"
          ? "Ошибка оценки"
          : "Нет оценки";
    return (
      <div className={className} data-tone="none">
        <span className={styles.score} aria-hidden="true">
          –
        </span>
        <span className={styles.caption}>{label}</span>
      </div>
    );
  }

  const { score, verdict } = evaluation;
  const filled = Math.round(score / SEGMENTS);
  return (
    <div
      className={className}
      data-tone={verdict ?? "skip"}
      role="img"
      aria-label={`Балл ${score} из 100${verdict ? `, ${VERDICT_LABELS[verdict]}` : ""}`}
    >
      <span className={styles.score}>{score}</span>
      <span className={styles.bars} aria-hidden="true">
        {Array.from({ length: SEGMENTS }, (_, index) => (
          <span key={index} className={index < filled ? styles.on : styles.off} />
        ))}
      </span>
      {size === "large" && verdict && <span className={styles.caption}>{VERDICT_LABELS[verdict]}</span>}
    </div>
  );
}

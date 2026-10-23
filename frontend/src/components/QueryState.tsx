import type { ReactNode } from "react";

import { errorText } from "../lib/errors";
import { Button } from "./Button";
import styles from "./QueryState.module.css";

interface QueryLike {
  isPending: boolean;
  error: unknown;
  refetch: () => unknown;
}

interface Props {
  query: QueryLike;
  /** Что грузится — для подписи «Загружаем вакансии…». */
  what: string;
  children: ReactNode;
}

/** Загрузка и ошибка запроса в одном виде на всех экранах; данные — в children. */
export function QueryState({ query, what, children }: Props) {
  if (query.isPending) {
    return (
      <p className={styles.loading} role="status">
        Загружаем {what}…
      </p>
    );
  }
  if (query.error) {
    return (
      <ErrorPanel error={query.error} onRetry={() => void query.refetch()}>
        Не удалось загрузить {what}.
      </ErrorPanel>
    );
  }
  return children;
}

interface ErrorPanelProps {
  error: unknown;
  onRetry?: () => void;
  children?: ReactNode;
}

export function ErrorPanel({ error, onRetry, children }: ErrorPanelProps) {
  return (
    <div className={styles.error} role="alert">
      <p>
        {children} {errorText(error)}
      </p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Повторить
        </Button>
      )}
    </div>
  );
}

/** Ошибка действия рядом с кнопкой, без панели. */
export function InlineError({ error, id }: { error: unknown; id?: string }) {
  if (!error) return null;
  return (
    <p className="error-text" role="alert" id={id}>
      {errorText(error)}
    </p>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className={styles.empty}>
      <h2>{title}</h2>
      {children && <p>{children}</p>}
    </div>
  );
}

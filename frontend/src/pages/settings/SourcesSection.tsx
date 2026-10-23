import { useQueryClient } from "@tanstack/react-query";

import { keys, useBackgroundTask, useRunSource, useSources } from "../../api/hooks";
import type { Source } from "../../api/models";
import { Button } from "../../components/Button";
import { EmptyState, InlineError, QueryState } from "../../components/QueryState";
import { formatDateTime } from "../../lib/format";
import { runStatsText, runStatusLabel } from "../../lib/sources";
import { isTaskFailed } from "../../lib/tasks";
import styles from "./settings.module.css";

export function SourcesSection() {
  const sources = useSources();
  return (
    <section id="sources" className={styles.section} aria-labelledby="sources-heading">
      <h2 id="sources-heading">Сбор вакансий</h2>
      <p className={styles.lead}>
        Источники обходятся по расписанию (по умолчанию раз в час). Запустить сбор можно и вручную.
      </p>
      <QueryState query={sources} what="источники">
        {sources.data?.length === 0 ? (
          <EmptyState title="Источников нет" />
        ) : (
          <ul className={styles.list}>
            {sources.data?.map((source) => (
              <SourceItem key={source.code} source={source} />
            ))}
          </ul>
        )}
      </QueryState>
    </section>
  );
}

function SourceItem({ source }: { source: Source }) {
  const client = useQueryClient();
  const run = useRunSource();
  const task = useBackgroundTask(() => {
    void client.invalidateQueries({ queryKey: keys.sources });
    void client.invalidateQueries({ queryKey: keys.vacancies });
  });
  const stats = runStatsText(source.last_run_stats);

  return (
    <li>
      <div className={styles.itemMain}>
        <strong>{source.code}</strong>
        <span className="muted">
          {source.is_enabled ? "" : "Выключен. "}
          Последний сбор: {runStatusLabel(source.last_run_status)}
          {source.last_run_finished_at && `, ${formatDateTime(source.last_run_finished_at)}`}
          {stats && `; ${stats}`}
        </span>
        {source.last_error && <span className="error-text">{source.last_error}</span>}
        <InlineError error={run.error ?? task.error} />
        {isTaskFailed(task.task) && (
          <span className="error-text">Сбор завершился ошибкой: {task.task?.error}</span>
        )}
      </div>
      <Button
        variant="secondary"
        disabled={!source.is_enabled}
        busy={run.isPending || task.running}
        onClick={() => run.mutate(source.code, { onSuccess: ({ task_id }) => task.start(task_id) })}
      >
        {task.running ? "Собираем…" : "Собрать сейчас"}
      </Button>
    </li>
  );
}

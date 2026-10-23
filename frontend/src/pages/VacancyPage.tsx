import { useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { keys, useBackgroundTask, useReevaluate, useSetApplication, useVacancy } from "../api/hooks";
import type { Evaluation, Vacancy } from "../api/models";
import { Button } from "../components/Button";
import { EmptyState, InlineError, QueryState } from "../components/QueryState";
import { ScoreMeter } from "../components/ScoreMeter";
import { StatusPicker } from "../components/StatusPicker";
import { VacancyMeta } from "../components/VacancyMeta";
import { ApiError } from "../lib/errors";
import { formatDateTime } from "../lib/format";
import { sanitizeHtml } from "../lib/html";
import { intInRange } from "../lib/queryParams";
import { isTaskFailed } from "../lib/tasks";
import styles from "./VacancyPage.module.css";

function NotFound() {
  return (
    <EmptyState title="Вакансия не найдена">
      Возможно, ссылка устарела. Вернитесь в <Link to="/">ленту</Link>.
    </EmptyState>
  );
}

export function VacancyPage() {
  // Нечисловой id в адресе не уходит в API.
  const id = intInRange(useParams().id ?? null, 1, Number.MAX_SAFE_INTEGER);
  return id === null ? <NotFound /> : <VacancyLoader id={id} />;
}

function VacancyLoader({ id }: { id: number }) {
  const vacancy = useVacancy(id);
  if (vacancy.error instanceof ApiError && vacancy.error.status === 404) return <NotFound />;
  return (
    <QueryState query={vacancy} what="вакансию">
      {vacancy.data && <VacancyCard vacancy={vacancy.data} />}
    </QueryState>
  );
}

function VacancyCard({ vacancy }: { vacancy: Vacancy }) {
  const setApplication = useSetApplication(vacancy.id);
  const description = vacancy.description ?? vacancy.short_description;
  return (
    <article className={styles.card}>
      <header className={styles.header}>
        <Link to="/" className={styles.back}>
          К ленте
        </Link>
        <h1 className={styles.title}>{vacancy.title}</h1>
        <VacancyMeta vacancy={vacancy} />
        <a href={vacancy.url} target="_blank" rel="noopener noreferrer" className={styles.external}>
          Открыть на {vacancy.source_code}
        </a>
      </header>

      <div className={styles.columns}>
        <section className={styles.description} aria-label="Описание вакансии">
          {vacancy.filter && !vacancy.filter.passed && (
            <p className={styles.rejected}>
              Фильтр отсеял вакансию: {vacancy.filter.reasons.join("; ")}.
            </p>
          )}
          {description ? (
            <div
              className={styles.prose}
              // Разметка источника, очищенная DOMPurify.
              dangerouslySetInnerHTML={{ __html: sanitizeHtml(description) }}
            />
          ) : (
            <p className="muted">Описание ещё не загружено.</p>
          )}
          {!vacancy.description && vacancy.short_description && (
            <p className="muted">
              Это краткое описание из списка. Полное загрузится, если вакансия пройдёт фильтр.
            </p>
          )}
        </section>

        <aside className={styles.aside}>
          <EvaluationPanel vacancy={vacancy} />
          <section className={styles.panel} aria-labelledby="application-heading">
            <h2 id="application-heading">Отклик</h2>
            <StatusPicker
              label="Статус отклика"
              value={vacancy.application?.status ?? null}
              disabled={setApplication.isPending}
              onChange={(status) => setApplication.mutate(status)}
            />
            {vacancy.application && (
              <p className="muted">
                Изменён {formatDateTime(vacancy.application.updated_at)}.{" "}
                <Link to="/applications">Журнал откликов</Link>
              </p>
            )}
            <InlineError error={setApplication.error} />
          </section>
        </aside>
      </div>
    </article>
  );
}

function EvaluationPanel({ vacancy }: { vacancy: Vacancy }) {
  const client = useQueryClient();
  const reevaluate = useReevaluate(vacancy.id);
  const task = useBackgroundTask(() => {
    void client.invalidateQueries({ queryKey: keys.vacancies });
  });
  const evaluation = vacancy.evaluation;

  const start = () => {
    reevaluate.mutate(undefined, { onSuccess: ({ task_id }) => task.start(task_id) });
  };

  return (
    <section className={styles.panel} aria-labelledby="evaluation-heading">
      <h2 id="evaluation-heading" className="visually-hidden">
        Оценка
      </h2>
      <ScoreMeter evaluation={evaluation} size="large" />
      {evaluation?.status === "failed" && evaluation.error && (
        <p className="muted">Модель не справилась: {evaluation.error}</p>
      )}
      {evaluation?.status === "done" && <EvaluationDetails evaluation={evaluation} />}
      <div className={styles.reevaluate}>
        <Button variant="secondary" busy={reevaluate.isPending || task.running} onClick={start}>
          {task.running ? "Оцениваем…" : evaluation ? "Оценить заново" : "Оценить"}
        </Button>
        {evaluation && (
          <span className="muted">
            {evaluation.model ?? "модель не указана"}, промпт {evaluation.prompt_version},{" "}
            {formatDateTime(evaluation.updated_at)}
          </span>
        )}
      </div>
      <InlineError error={reevaluate.error ?? task.error} />
      {isTaskFailed(task.task) && (
        <p className="error-text" role="alert">
          Оценка не удалась. Подробности — в логах воркера.
        </p>
      )}
    </section>
  );
}

function EvaluationDetails({ evaluation }: { evaluation: Evaluation }) {
  const matches = evaluation.matches ?? [];
  // Блокеры первыми: из-за них не откликаются.
  const gaps = [...(evaluation.gaps ?? [])].sort(
    (a, b) => Number(b.severity === "blocker") - Number(a.severity === "blocker"),
  );
  const dealbreakers = evaluation.dealbreakers ?? [];
  return (
    <>
      {dealbreakers.length > 0 && (
        <div className={styles.dealbreakers}>
          <h3>Мешает отклику</h3>
          <ul>
            {dealbreakers.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <h3>Совпадает</h3>
        {matches.length === 0 ? (
          <p className="muted">Совпадений модель не нашла.</p>
        ) : (
          <ul className={styles.matches}>
            {matches.map((match, index) => (
              <li key={index}>
                <span className={styles.requirement}>{match.requirement}</span>
                <span className={styles.evidence}>{match.evidence}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3>Не хватает</h3>
        {gaps.length === 0 ? (
          <p className="muted">Пробелов нет.</p>
        ) : (
          <ul className={styles.gaps}>
            {gaps.map((gap, index) => (
              <li key={index} className={gap.severity === "blocker" ? styles.blocker : undefined}>
                {gap.requirement}
                {gap.severity === "blocker" && <span className={styles.tag}>обязательно</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

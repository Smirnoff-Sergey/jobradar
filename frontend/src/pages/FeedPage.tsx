import { Link, useSearchParams } from "react-router";

import { useSources, useVacancies } from "../api/hooks";
import type { VacancyListItem } from "../api/models";
import { Pager } from "../components/Pager";
import { EmptyState, QueryState } from "../components/QueryState";
import rows from "../components/rows.module.css";
import { ScoreMeter } from "../components/ScoreMeter";
import { Select } from "../components/Select";
import { StatusPill } from "../components/StatusPill";
import { VacancyMeta } from "../components/VacancyMeta";
import { type FeedFilters, filtersToParams, filtersToQuery, parseFilters } from "../lib/feedParams";
import {
  APPLICATION_STATUSES,
  APPLICATION_STATUS_LABELS,
  VERDICTS,
  VERDICT_LABELS,
} from "../lib/labels";
import { optionsFrom } from "../lib/options";
import styles from "./FeedPage.module.css";

const STATUS_OPTIONS = optionsFrom(["passed", "rejected", "all"], {
  passed: "Прошли фильтр",
  rejected: "Отсеянные",
  all: "Все",
});
const VERDICT_OPTIONS = optionsFrom(VERDICTS, VERDICT_LABELS, "Любой");
const SCORE_OPTIONS = [
  { value: "", label: "Любой" },
  ...[40, 50, 60, 70, 80, 90].map((step) => ({ value: String(step), label: `от ${step}` })),
];
const APPLICATION_OPTIONS = optionsFrom(APPLICATION_STATUSES, APPLICATION_STATUS_LABELS, "Любой");
const SORT_OPTIONS = optionsFrom(["published", "score"], {
  published: "Сначала новые",
  score: "По баллу",
});

export function FeedPage() {
  const [params, setParams] = useSearchParams();
  const filters = parseFilters(params);
  const vacancies = useVacancies(filtersToQuery(filters));
  const sources = useSources();

  // Любой фильтр, кроме страницы, возвращает на первую страницу.
  const update = (patch: Partial<FeedFilters>) => {
    setParams(filtersToParams({ ...filters, page: 1, ...patch }));
  };
  const isDefault = filtersToParams(filters).size === 0;
  const page = vacancies.data;

  return (
    <div className={styles.page}>
      <div className={styles.heading}>
        <h1>Лента</h1>
        {!isDefault && (
          <button type="button" className={styles.reset} onClick={() => setParams({})}>
            Сбросить фильтры
          </button>
        )}
      </div>

      <div className={styles.filters} role="search" aria-label="Фильтры ленты">
        <Select
          label="Показать"
          value={filters.status}
          onChange={(status) => update({ status })}
          options={STATUS_OPTIONS}
        />
        <Select
          label="Вердикт"
          value={filters.verdict ?? ""}
          onChange={(verdict) => update({ verdict: verdict || null })}
          options={VERDICT_OPTIONS}
        />
        <Select
          label="Балл"
          value={filters.scoreMin === null ? "" : String(filters.scoreMin)}
          onChange={(value) => update({ scoreMin: value ? Number(value) : null })}
          options={SCORE_OPTIONS}
        />
        <Select
          label="Источник"
          value={filters.source ?? ""}
          onChange={(source) => update({ source: source || null })}
          options={[
            { value: "", label: "Все" },
            ...(sources.data ?? []).map((s) => ({ value: s.code, label: s.code })),
          ]}
        />
        <Select
          label="Отклик"
          value={filters.applicationStatus ?? ""}
          onChange={(status) => update({ applicationStatus: status || null })}
          options={APPLICATION_OPTIONS}
        />
        <Select
          label="Порядок"
          value={filters.sort}
          onChange={(sort) => update({ sort })}
          options={SORT_OPTIONS}
        />
      </div>

      <QueryState query={vacancies} what="вакансии">
        {page?.total === 0 && (
          <EmptyState title={isDefault ? "Вакансий пока нет" : "Под фильтры ничего не подошло"}>
            {isDefault ? (
              <>
                Запустите сбор в <Link to="/settings">настройках</Link> или подождите сбора по
                расписанию.
              </>
            ) : (
              "Ослабьте фильтры или сбросьте их."
            )}
          </EmptyState>
        )}
        {page && page.total > 0 && (
          <>
            {page.items.length > 0 && (
              <ol className={rows.list} aria-busy={vacancies.isPlaceholderData || undefined}>
                {page.items.map((vacancy) => (
                  <VacancyRow key={vacancy.id} vacancy={vacancy} />
                ))}
              </ol>
            )}
            <Pager
              page={filters.page}
              total={page.total}
              onPage={(next) => setParams(filtersToParams({ ...filters, page: next }))}
              nouns={["вакансии", "вакансий", "вакансий"]}
            />
          </>
        )}
      </QueryState>
    </div>
  );
}

function VacancyRow({ vacancy }: { vacancy: VacancyListItem }) {
  const reasons = vacancy.filter && !vacancy.filter.passed ? vacancy.filter.reasons : [];
  return (
    <li className={`${rows.row} ${styles.row}`}>
      <ScoreMeter evaluation={vacancy.evaluation} />
      <div className={styles.body}>
        <Link to={`/vacancies/${vacancy.id}`} className={`${rows.title} ${styles.title}`}>
          {vacancy.title}
        </Link>
        <VacancyMeta vacancy={vacancy} />
        {reasons.length > 0 && <p className="error-text">Отсеяна: {reasons.join("; ")}</p>}
      </div>
      {vacancy.application && <StatusPill status={vacancy.application.status} />}
    </li>
  );
}

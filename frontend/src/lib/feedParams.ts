// Фильтры ленты живут в адресной строке: ссылку можно сохранить, «Назад» возвращает фильтр.
import type { ApplicationStatus, VacancyQuery, Verdict } from "../api/models";
import { APPLICATION_STATUSES, VERDICTS } from "./labels";
import { intInRange, oneOf, PAGE_SIZE, pageOffset, parsePage } from "./queryParams";

export type FilterStatus = NonNullable<VacancyQuery["status"]>;
export type FeedSort = NonNullable<VacancyQuery["sort"]>;

export interface FeedFilters {
  status: FilterStatus;
  verdict: Verdict | null;
  scoreMin: number | null;
  source: string | null;
  applicationStatus: ApplicationStatus | null;
  sort: FeedSort;
  page: number;
}

export const DEFAULT_FILTERS: FeedFilters = {
  status: "passed",
  verdict: null,
  scoreMin: null,
  source: null,
  applicationStatus: null,
  sort: "published",
  page: 1,
};

/** Неверные значения в адресе молча заменяются значениями по умолчанию. */
export function parseFilters(params: URLSearchParams): FeedFilters {
  return {
    status: oneOf(params.get("status"), ["passed", "rejected", "all"]) ?? DEFAULT_FILTERS.status,
    verdict: oneOf(params.get("verdict"), VERDICTS),
    scoreMin: intInRange(params.get("score_min"), 0, 100),
    source: params.get("source") || null,
    applicationStatus: oneOf(params.get("application"), APPLICATION_STATUSES),
    sort: oneOf(params.get("sort"), ["published", "score"]) ?? DEFAULT_FILTERS.sort,
    page: parsePage(params.get("page")),
  };
}

/** В адрес попадают только значения, отличные от умолчаний. */
export function filtersToParams(filters: FeedFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.status !== DEFAULT_FILTERS.status) params.set("status", filters.status);
  if (filters.verdict) params.set("verdict", filters.verdict);
  if (filters.scoreMin !== null) params.set("score_min", String(filters.scoreMin));
  if (filters.source) params.set("source", filters.source);
  if (filters.applicationStatus) params.set("application", filters.applicationStatus);
  if (filters.sort !== DEFAULT_FILTERS.sort) params.set("sort", filters.sort);
  if (filters.page > 1) params.set("page", String(filters.page));
  return params;
}

export function filtersToQuery(filters: FeedFilters): VacancyQuery {
  return {
    status: filters.status,
    verdict: filters.verdict,
    score_min: filters.scoreMin,
    source: filters.source,
    application_status: filters.applicationStatus,
    sort: filters.sort,
    limit: PAGE_SIZE,
    offset: pageOffset(filters.page),
  };
}

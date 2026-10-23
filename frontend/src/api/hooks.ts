// Запросы к API через TanStack Query. Ключи кэша собраны в одном месте, чтобы мутации
// точно знали, что сбросить.
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { isTaskFinished, pollInterval } from "../lib/tasks";
import { api, unwrap } from "./client";
import type {
  ApplicationQuery,
  ApplicationStatus,
  SearchProfileUpdate,
  TaskStatus,
  VacancyQuery,
} from "./models";

export const keys = {
  me: ["me"] as const,
  vacancies: ["vacancies"] as const,
  vacancyList: (query: VacancyQuery) => ["vacancies", "list", query] as const,
  vacancy: (id: number) => ["vacancies", "detail", id] as const,
  applications: ["applications"] as const,
  applicationList: (query: ApplicationQuery) => ["applications", "list", query] as const,
  application: (id: number) => ["applications", "detail", id] as const,
  resumes: ["resumes"] as const,
  searchProfile: ["search-profile"] as const,
  sources: ["sources"] as const,
  llmUsage: ["llm-usage"] as const,
  task: (id: string) => ["tasks", id] as const,
};

/** Отклик виден и в ленте, и в карточке, и в журнале — сбрасываются все три. */
function invalidateApplications(client: QueryClient): Promise<void> {
  return Promise.all([
    client.invalidateQueries({ queryKey: keys.vacancies }),
    client.invalidateQueries({ queryKey: keys.applications }),
  ]).then(() => undefined);
}

/** poll — опрашивать, пока пользователь привязывает чат в Telegram. */
export function useMe({ poll = false }: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => unwrap(api.GET("/api/v1/auth/me")),
    refetchInterval: poll ? 3000 : false,
  });
}

export function useVacancies(query: VacancyQuery) {
  return useQuery({
    queryKey: keys.vacancyList(query),
    queryFn: () => unwrap(api.GET("/api/v1/vacancies", { params: { query } })),
    // При смене страницы или фильтра старый список остаётся на экране до прихода нового.
    placeholderData: keepPreviousData,
  });
}

export function useVacancy(id: number) {
  return useQuery({
    queryKey: keys.vacancy(id),
    queryFn: () =>
      unwrap(api.GET("/api/v1/vacancies/{vacancy_id}", { params: { path: { vacancy_id: id } } })),
    // Пока оценка в работе, карточка сама подтянет результат.
    refetchInterval: (query) =>
      query.state.data?.evaluation?.status === "pending" ? 5000 : false,
  });
}

export function useSetApplication(vacancyId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (status: ApplicationStatus) =>
      unwrap(
        api.PUT("/api/v1/vacancies/{vacancy_id}/application", {
          params: { path: { vacancy_id: vacancyId } },
          body: { status },
        }),
      ),
    onSuccess: () => invalidateApplications(client),
  });
}

export function useReevaluate(vacancyId: number) {
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/vacancies/{vacancy_id}/evaluate", {
          params: { path: { vacancy_id: vacancyId } },
        }),
      ),
  });
}

export function useApplications(query: ApplicationQuery) {
  return useQuery({
    queryKey: keys.applicationList(query),
    queryFn: () => unwrap(api.GET("/api/v1/applications", { params: { query } })),
    placeholderData: keepPreviousData,
  });
}

export function useApplication(id: number | null) {
  return useQuery({
    queryKey: keys.application(id ?? 0),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/applications/{application_id}", {
          params: { path: { application_id: id ?? 0 } },
        }),
      ),
    enabled: id !== null,
  });
}

export function useUpdateApplication(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { status?: ApplicationStatus; notes?: string }) =>
      unwrap(
        api.PATCH("/api/v1/applications/{application_id}", {
          params: { path: { application_id: id } },
          body,
        }),
      ),
    onSuccess: () => invalidateApplications(client),
  });
}

export function useResumes() {
  return useQuery({
    queryKey: keys.resumes,
    queryFn: () => unwrap(api.GET("/api/v1/resumes")),
  });
}

/** Смена текста резюме удаляет его оценки — лента тоже устаревает. */
function invalidateResumes(client: QueryClient): Promise<void> {
  return Promise.all([
    client.invalidateQueries({ queryKey: keys.resumes }),
    client.invalidateQueries({ queryKey: keys.vacancies }),
  ]).then(() => undefined);
}

export function useCreateResume() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { title: string; text: string }) =>
      unwrap(api.POST("/api/v1/resumes", { body: { ...body, make_active: true } })),
    onSuccess: () => invalidateResumes(client),
  });
}

export function useUpdateResume() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; title?: string; text?: string; is_active?: boolean }) =>
      unwrap(api.PUT("/api/v1/resumes/{resume_id}", { params: { path: { resume_id: id } }, body })),
    onSuccess: () => invalidateResumes(client),
  });
}

export function useSearchProfile() {
  return useQuery({
    queryKey: keys.searchProfile,
    queryFn: () => unwrap(api.GET("/api/v1/search-profile")),
  });
}

export function useSaveSearchProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SearchProfileUpdate) => unwrap(api.PUT("/api/v1/search-profile", { body })),
    onSuccess: (result) => {
      client.setQueryData(keys.searchProfile, result.profile);
    },
  });
}

export function useSources() {
  return useQuery({
    queryKey: keys.sources,
    queryFn: () => unwrap(api.GET("/api/v1/sources")),
  });
}

export function useRunSource() {
  return useMutation({
    mutationFn: (code: string) =>
      unwrap(api.POST("/api/v1/sources/{code}/run", { params: { path: { code } } })),
  });
}

export function useLLMUsage() {
  return useQuery({
    queryKey: keys.llmUsage,
    queryFn: () => unwrap(api.GET("/api/v1/llm/usage")),
  });
}

export function useCreateTelegramLink() {
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/telegram/link")),
  });
}

export function useDeleteTelegramLink() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/telegram/link")),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.me }),
  });
}

/**
 * Следит за фоновой задачей до завершения и один раз вызывает onFinish.
 * start(id) — начать следить за задачей, которую вернул API.
 */
export function useBackgroundTask(onFinish: (task: TaskStatus) => void) {
  const [taskId, setTaskId] = useState<string | null>(null);
  const finishRef = useRef(onFinish);
  const reportedRef = useRef<string | null>(null);

  useEffect(() => {
    finishRef.current = onFinish;
  });

  const query = useQuery({
    queryKey: keys.task(taskId ?? ""),
    queryFn: () =>
      unwrap(api.GET("/api/v1/tasks/{task_id}", { params: { path: { task_id: taskId ?? "" } } })),
    enabled: taskId !== null,
    // Ошибка запроса статуса (API перезапущен, сеть) останавливает опрос: иначе он шёл бы вечно.
    refetchInterval: (state) =>
      state.state.status === "error" || isTaskFinished(state.state.data)
        ? false
        : pollInterval(state.state.dataUpdateCount),
    retry: false,
  });

  const task = query.data;
  useEffect(() => {
    if (task && isTaskFinished(task) && reportedRef.current !== task.task_id) {
      reportedRef.current = task.task_id;
      finishRef.current(task);
    }
  }, [task]);

  return {
    start: setTaskId,
    task: taskId === null ? undefined : task,
    running: taskId !== null && !query.isError && !isTaskFinished(task),
    error: query.error,
  };
}

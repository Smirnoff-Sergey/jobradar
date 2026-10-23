// Фоновые задачи Celery: API отдаёт сырое состояние задачи.
import type { TaskStatus } from "../api/models";

const FINISHED_STATES = new Set(["SUCCESS", "FAILURE", "REVOKED"]);

/** PENDING значит и «ещё в очереди», и «такой задачи нет» — Celery их не различает. */
export function isTaskFinished(task: TaskStatus | undefined): boolean {
  return task !== undefined && FINISHED_STATES.has(task.state);
}

export function isTaskFailed(task: TaskStatus | undefined): boolean {
  return task !== undefined && (task.state === "FAILURE" || task.state === "REVOKED");
}

/** Интервал опроса растёт: 1 с, 2 с, 4 с... до 10 с — длинная задача не грузит API. */
export function pollInterval(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 10_000);
}

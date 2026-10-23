// Ошибки API приходят в едином формате {"error": {"code", "message", "details"}}.

export interface ValidationIssue {
  loc: (string | number)[];
  msg: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ValidationIssue[];

  constructor(status: number, code: string, message: string, details: ValidationIssue[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isIssue(value: unknown): value is ValidationIssue {
  return isRecord(value) && Array.isArray(value.loc) && typeof value.msg === "string";
}

/** Превращает тело ответа с ошибкой в ApiError; незнакомый формат (nginx, прокси) — тоже. */
export function toApiError(body: unknown, status: number): ApiError {
  const error = isRecord(body) ? body.error : undefined;
  if (isRecord(error) && typeof error.code === "string" && typeof error.message === "string") {
    const details = Array.isArray(error.details) ? error.details.filter(isIssue) : [];
    return new ApiError(status, error.code, error.message, details);
  }
  return new ApiError(status, `http_${status}`, `Сервер ответил ошибкой ${status}`);
}

/** Ошибки валидации по полям тела запроса: {"title": "..."} из loc ["body", "title"]. */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  const result: Record<string, string> = {};
  for (const issue of error.details) {
    const [where, field] = issue.loc;
    if (where === "body" && field !== undefined) result[String(field)] ??= issue.msg;
  }
  return result;
}

/** Текст ошибки для человека. */
export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  // fetch бросает TypeError, когда сервер недоступен или соединение оборвалось.
  if (error instanceof TypeError) return "Нет связи с сервером. Проверьте, что API запущен.";
  return "Что-то пошло не так. Обновите страницу.";
}

import createClient from "openapi-fetch";

import { toApiError } from "../lib/errors";
import type { paths } from "./schema";
import { type TokenPair, tokens } from "./tokens";

type Fetch = (request: Request) => Promise<Response>;

const AUTH_PATHS = ["/api/v1/auth/login", "/api/v1/auth/refresh"];

/**
 * fetch с JWT: подставляет access-токен, при 401 один раз обновляет пару по refresh-токену
 * и повторяет запрос. Параллельные запросы ждут одно общее обновление.
 */
export function createAuthFetch(baseFetch: Fetch = (request) => fetch(request)): Fetch {
  let refreshing: Promise<boolean> | null = null;

  async function refreshTokens(): Promise<boolean> {
    const refreshToken = tokens.refresh();
    if (refreshToken === null) return false;
    const response = await baseFetch(
      new Request(new URL("/api/v1/auth/refresh", location.origin), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      }),
    );
    if (response.status === 401) {
      // Refresh-токен истёк или подписан старым секретом — нужен новый вход.
      tokens.clear();
      return false;
    }
    if (!response.ok) throw toApiError(await response.json().catch(() => null), response.status);
    tokens.save((await response.json()) as TokenPair);
    return true;
  }

  function refreshOnce(): Promise<boolean> {
    refreshing ??= refreshTokens().finally(() => {
      refreshing = null;
    });
    return refreshing;
  }

  function withAccess(request: Request): Request {
    const access = tokens.access();
    if (access !== null) request.headers.set("Authorization", `Bearer ${access}`);
    return request;
  }

  return async (request) => {
    if (AUTH_PATHS.includes(new URL(request.url).pathname)) return baseFetch(request);
    // Тело запроса читается один раз — для повтора нужна копия.
    const retry = request.clone();
    // После перезагрузки страницы access-токена нет, а refresh есть.
    if (tokens.access() === null && tokens.isLoggedIn()) await refreshOnce();
    const response = await baseFetch(withAccess(request));
    if (response.status !== 401 || !tokens.isLoggedIn()) return response;
    return (await refreshOnce()) ? baseFetch(withAccess(retry)) : response;
  };
}

export const api = createClient<paths>({ baseUrl: location.origin, fetch: createAuthFetch() });

interface ApiResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Данные успешного ответа или ApiError — удобно для TanStack Query. */
export async function unwrap<T>(request: Promise<ApiResult<T>>): Promise<T> {
  const { data, error, response } = await request;
  if (!response.ok) throw toApiError(error, response.status);
  return data as T;
}

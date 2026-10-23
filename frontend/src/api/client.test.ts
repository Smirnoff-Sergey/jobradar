import { beforeEach, describe, expect, it, vi } from "vitest";

// Модуль клиента читает location и localStorage при загрузке — подменяем до импорта.
vi.hoisted(() => {
  const store = new Map<string, string>();
  vi.stubGlobal("location", { origin: "http://jobradar.test" });
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => store.set(key, value),
    removeItem: (key: string) => store.delete(key),
  });
});

const { createAuthFetch } = await import("./client");
const { tokens } = await import("./tokens");

const API = "http://jobradar.test/api/v1";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Сервер: access-токен «fresh» действует, остальные — нет; refresh выдаёт «fresh». */
function fakeServer(options: { refreshStatus?: number } = {}) {
  const calls: { path: string; auth: string | null }[] = [];
  const handler = vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname;
    calls.push({ path, auth: request.headers.get("Authorization") });
    if (path === "/api/v1/auth/refresh") {
      const status = options.refreshStatus ?? 200;
      if (status !== 200) return json(status, { error: { code: "invalid_token", message: "Истёк" } });
      const body = (await request.json()) as { refresh_token: string };
      return json(200, { access_token: "fresh", refresh_token: `${body.refresh_token}+1` });
    }
    if (request.headers.get("Authorization") !== "Bearer fresh") {
      return json(401, { error: { code: "invalid_token", message: "Срок действия токена истёк" } });
    }
    return json(200, { ok: true, body: request.method === "POST" ? await request.text() : null });
  });
  return { handler, calls };
}

beforeEach(() => {
  tokens.clear();
});

describe("createAuthFetch", () => {
  it("подставляет access-токен", async () => {
    tokens.save({ access_token: "fresh", refresh_token: "r" });
    const server = fakeServer();
    const response = await createAuthFetch(server.handler)(new Request(`${API}/auth/me`));
    expect(response.status).toBe(200);
    expect(server.calls).toEqual([{ path: "/api/v1/auth/me", auth: "Bearer fresh" }]);
  });

  it("после перезагрузки страницы сначала обновляет токен по refresh", async () => {
    // После перезагрузки access-токена в памяти нет, refresh остался в localStorage.
    localStorage.setItem("jobradar.refresh", "r");
    const server = fakeServer();
    const response = await createAuthFetch(server.handler)(new Request(`${API}/auth/me`));
    expect(response.status).toBe(200);
    expect(server.calls).toEqual([
      { path: "/api/v1/auth/refresh", auth: null },
      { path: "/api/v1/auth/me", auth: "Bearer fresh" },
    ]);
  });

  it("на 401 обновляет токен и повторяет запрос с тем же телом", async () => {
    tokens.save({ access_token: "stale", refresh_token: "r" });
    const server = fakeServer();
    const response = await createAuthFetch(server.handler)(
      new Request(`${API}/resumes`, { method: "POST", body: "{\"title\":\"x\"}" }),
    );
    expect(response.status).toBe(200);
    // Тело запроса дошло и при повторе.
    expect(await response.json()).toEqual({ ok: true, body: "{\"title\":\"x\"}" });
    expect(server.calls.map((call) => call.path)).toEqual([
      "/api/v1/resumes",
      "/api/v1/auth/refresh",
      "/api/v1/resumes",
    ]);
    expect(tokens.refresh()).toBe("r+1");
  });

  it("параллельные запросы ждут одно обновление", async () => {
    tokens.save({ access_token: "stale", refresh_token: "r" });
    const server = fakeServer();
    const authFetch = createAuthFetch(server.handler);
    const responses = await Promise.all([
      authFetch(new Request(`${API}/vacancies`)),
      authFetch(new Request(`${API}/sources`)),
    ]);
    expect(responses.map((r) => r.status)).toEqual([200, 200]);
    expect(server.calls.filter((call) => call.path === "/api/v1/auth/refresh")).toHaveLength(1);
  });

  it("истёкший refresh-токен — выход", async () => {
    tokens.save({ access_token: "stale", refresh_token: "r" });
    const listener = vi.fn();
    const unsubscribe = tokens.subscribe(listener);
    const server = fakeServer({ refreshStatus: 401 });
    const response = await createAuthFetch(server.handler)(new Request(`${API}/vacancies`));
    unsubscribe();
    expect(response.status).toBe(401);
    expect(tokens.isLoggedIn()).toBe(false);
    expect(listener).toHaveBeenCalled();
  });

  it("запросы входа идут без токена и без обновления", async () => {
    const server = fakeServer();
    const response = await createAuthFetch(server.handler)(
      new Request(`${API}/auth/login`, { method: "POST", body: "{}" }),
    );
    expect(response.status).toBe(401);
    expect(server.calls).toEqual([{ path: "/api/v1/auth/login", auth: null }]);
  });
});

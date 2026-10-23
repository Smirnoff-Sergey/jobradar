import { describe, expect, it } from "vitest";

import { ApiError, errorText, fieldErrors, toApiError } from "./errors";

describe("toApiError", () => {
  it("разбирает единый формат ошибок API", () => {
    const error = toApiError({ error: { code: "not_found", message: "Вакансия не найдена" } }, 404);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: "not_found", message: "Вакансия не найдена" });
  });

  it("чужой формат (nginx, прокси) — общая ошибка со статусом", () => {
    const error = toApiError("<html>502 Bad Gateway</html>", 502);
    expect(error).toMatchObject({ status: 502, code: "http_502" });
  });
});

describe("fieldErrors", () => {
  it("ошибки валидации раскладываются по полям тела", () => {
    const error = toApiError(
      {
        error: {
          code: "validation_error",
          message: "Некорректные данные запроса",
          details: [
            { type: "string_too_short", loc: ["body", "text"], msg: "Слишком коротко" },
            { type: "missing", loc: ["body", "text"], msg: "Второе сообщение не нужно" },
            { type: "int_parsing", loc: ["query", "limit"], msg: "Не число" },
            { broken: true },
          ],
        },
      },
      422,
    );
    expect(fieldErrors(error)).toEqual({ text: "Слишком коротко" });
  });

  it("не ApiError — пусто", () => {
    expect(fieldErrors(new Error("x"))).toEqual({});
  });
});

describe("errorText", () => {
  it("сетевая ошибка fetch — про связь с сервером", () => {
    expect(errorText(new TypeError("Failed to fetch"))).toMatch(/Нет связи/);
  });

  it("ApiError — сообщение сервера", () => {
    expect(errorText(new ApiError(409, "conflict", "Источник выключен"))).toBe("Источник выключен");
  });
});

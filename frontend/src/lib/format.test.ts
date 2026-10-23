import { describe, expect, it } from "vitest";

import { formatAge, formatSalary, plural } from "./format";

const salary = (from: number | null, to: number | null, gross: boolean | null = null) => ({
  salary_from: from,
  salary_to: to,
  salary_currency: "RUB",
  salary_gross: gross,
});

describe("formatSalary", () => {
  it("вилка в тысячах с общей единицей", () => {
    expect(formatSalary(salary(250_000, 300_000, false))).toBe("250–300 тыс ₽ на руки");
  });

  it("только нижняя или верхняя граница", () => {
    expect(formatSalary(salary(200_000, null, true))).toBe("от 200 тыс ₽ до вычета");
    expect(formatSalary(salary(null, 150_000))).toBe("до 150 тыс ₽");
  });

  it("одинаковые границы — одно число", () => {
    expect(formatSalary(salary(180_000, 180_000))).toBe("180 тыс ₽");
  });

  it("не круглые тысячи — с одним знаком, меньше тысячи — как есть", () => {
    expect(formatSalary({ ...salary(7_500, 10_000), salary_currency: "USD" })).toBe(
      "7,5–10 тыс $",
    );
    expect(formatSalary({ ...salary(800, null), salary_currency: "EUR" })).toBe("от 800 €");
  });

  it("неизвестная валюта показывается как есть", () => {
    expect(formatSalary({ ...salary(100_000, null), salary_currency: "₽" })).toBe("от 100 тыс ₽");
  });

  it("нет зарплаты — null", () => {
    expect(formatSalary(salary(null, null))).toBeNull();
  });
});

describe("formatAge", () => {
  const now = new Date(2026, 9, 23, 12, 0);

  it("сегодня, вчера, дни", () => {
    expect(formatAge(new Date(2026, 9, 23, 1, 0).toISOString(), now)).toBe("сегодня");
    expect(formatAge(new Date(2026, 9, 22, 23, 0).toISOString(), now)).toBe("вчера");
    expect(formatAge(new Date(2026, 9, 20).toISOString(), now)).toBe("3 дня назад");
    expect(formatAge(new Date(2026, 9, 18).toISOString(), now)).toBe("5 дней назад");
  });

  it("дальше недели — дата", () => {
    expect(formatAge(new Date(2026, 8, 1).toISOString(), now)).toBe("1 сентября");
  });
});

describe("plural", () => {
  it.each([
    [1, "день"],
    [2, "дня"],
    [5, "дней"],
    [11, "дней"],
    [12, "дней"],
    [21, "день"],
    [22, "дня"],
    [112, "дней"],
  ])("%i — %s", (count, expected) => {
    expect(plural(count, "день", "дня", "дней")).toBe(expected);
  });
});

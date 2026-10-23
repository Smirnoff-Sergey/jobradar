// Форматирование значений для интерфейса.

const whole = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const thousands = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

function currencySymbol(currency: string | null): string {
  if (currency === null) return "";
  try {
    const parts = new Intl.NumberFormat("ru-RU", { style: "currency", currency }).formatToParts(0);
    return parts.find((part) => part.type === "currency")?.value ?? currency;
  } catch {
    // Не ISO-код (например, уже символ) — показываем как пришло.
    return currency;
  }
}

/** От тысячи — в тысячах с одним знаком: «7,5 тыс», «250 тыс». */
function amount(value: number): string {
  return value >= 1000 ? `${thousands.format(value / 1000)} тыс` : whole.format(value);
}

export interface Salary {
  salary_from: number | null;
  salary_to: number | null;
  salary_currency: string | null;
  salary_gross: boolean | null;
}

/** «250–300 тыс ₽ на руки», «от 200 тыс ₽», «до 5 000 $»; null — зарплата не указана. */
export function formatSalary(salary: Salary): string | null {
  const { salary_from: from, salary_to: to } = salary;
  let range: string;
  if (from !== null && to !== null && from !== to) {
    // «250–300 тыс», а не «250 тыс–300 тыс»: единица общая.
    const [left, right] = [amount(from), amount(to)];
    range = left.endsWith(" тыс") && right.endsWith(" тыс") ? `${left.slice(0, -4)}–${right}` : `${left}–${right}`;
  } else if (from !== null) {
    range = to === from ? amount(from) : `от ${amount(from)}`;
  } else if (to !== null) {
    range = `до ${amount(to)}`;
  } else {
    return null;
  }
  const symbol = currencySymbol(salary.salary_currency);
  const taxes =
    salary.salary_gross === null ? "" : salary.salary_gross ? " до вычета" : " на руки";
  return `${range}${symbol ? ` ${symbol}` : ""}${taxes}`;
}

const dateFormat = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" });
const dateTimeFormat = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

const DAY_MS = 24 * 60 * 60 * 1000;

/** «сегодня», «вчера», «3 дня назад», дальше недели — дата. */
export function formatAge(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const startOfDay = (value: Date) =>
    new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const days = Math.round((startOfDay(now) - startOfDay(date)) / DAY_MS);
  if (days <= 0) return "сегодня";
  if (days === 1) return "вчера";
  if (days < 7) return `${days} ${plural(days, "день", "дня", "дней")} назад`;
  return dateFormat.format(date);
}

export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso));
}

/** Русское склонение: 1 день, 2 дня, 5 дней, 21 день. */
export function plural(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

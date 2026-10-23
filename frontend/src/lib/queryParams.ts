// Разбор параметров адресной строки: неверное значение — null, а не исключение.

export const PAGE_SIZE = 20;

export function oneOf<T extends string>(value: string | null, allowed: readonly T[]): T | null {
  return allowed.find((item) => item === value) ?? null;
}

export function intInRange(value: string | null, min: number, max: number): number | null {
  if (value === null || !/^\d+$/.test(value)) return null;
  const number = Number(value);
  return number >= min && number <= max ? number : null;
}

/** Номер страницы из ?page=: целое от 1, иначе первая. */
export function parsePage(value: string | null): number {
  return intInRange(value, 1, 10_000) ?? 1;
}

export function pageOffset(page: number): number {
  return (page - 1) * PAGE_SIZE;
}

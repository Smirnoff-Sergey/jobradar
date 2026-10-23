// Варианты выпадающих списков из значений API и их подписей.

export interface Option<T extends string> {
  value: T;
  label: string;
}

/** anyLabel — первый пункт «без фильтра» со значением "". */
export function optionsFrom<T extends string>(values: readonly T[], labels: Record<T, string>): Option<T>[];
export function optionsFrom<T extends string>(
  values: readonly T[],
  labels: Record<T, string>,
  anyLabel: string,
): Option<T | "">[];
export function optionsFrom<T extends string>(
  values: readonly T[],
  labels: Record<T, string>,
  anyLabel?: string,
): Option<T | "">[] {
  const options: Option<T | "">[] = values.map((value) => ({ value, label: labels[value] }));
  return anyLabel === undefined ? options : [{ value: "", label: anyLabel }, ...options];
}

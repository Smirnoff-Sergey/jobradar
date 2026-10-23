// Итог сбора источника: поля CollectStats из backend.

const RUN_STATUS_LABELS: Record<string, string> = {
  success: "успешно",
  failed: "с ошибкой",
  skipped: "пропущен: идёт другой сбор",
  disabled: "источник выключен",
};

export function runStatusLabel(status: string | null): string {
  if (status === null) return "ещё не запускался";
  return RUN_STATUS_LABELS[status] ?? status;
}

function count(stats: Record<string, unknown>, key: string): number | null {
  const value = stats[key];
  return typeof value === "number" ? value : null;
}

/** «получено 910, изменилось 3, снято 0, описаний в очереди 2». */
export function runStatsText(stats: Record<string, unknown> | null | undefined): string | null {
  if (!stats) return null;
  const parts: string[] = [];
  const fields: [key: string, label: string][] = [
    ["received", "получено"],
    ["changed", "изменилось"],
    ["deactivated", "снято"],
    ["details_queued", "описаний в очереди"],
  ];
  for (const [key, label] of fields) {
    const value = count(stats, key);
    if (value !== null) parts.push(`${label} ${value}`);
  }
  if (stats.deactivation_skipped === true) parts.push("снятие пропущено: обход неполный");
  return parts.length > 0 ? parts.join(", ") : null;
}

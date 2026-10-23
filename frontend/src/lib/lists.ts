/** Список из текста: по строкам и запятым, без пустых и повторов (регистр не важен). */
export function parseList(text: string): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const raw of text.split(/[\n,]/)) {
    const item = raw.trim();
    const key = item.toLowerCase();
    if (item && !seen.has(key)) {
      seen.add(key);
      result.push(item);
    }
  }
  return result;
}

export function formatList(items: readonly string[]): string {
  return items.join("\n");
}

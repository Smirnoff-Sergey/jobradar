/** Знак: три деления «шкалы сигнала», как у балла вакансии. */
export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="var(--ink)" />
      <g fill="var(--apply)">
        <rect x="7" y="18" width="4" height="7" rx="1" />
        <rect x="14" y="12" width="4" height="13" rx="1" />
        <rect x="21" y="6" width="4" height="19" rx="1" />
      </g>
    </svg>
  );
}

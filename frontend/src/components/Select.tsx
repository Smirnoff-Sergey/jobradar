import type { Option } from "../lib/options";
import styles from "./Select.module.css";

interface Props<T extends string> {
  label: string;
  value: T;
  onChange: (value: T) => void;
  options: readonly Option<T>[];
}

/** Выпадающий список с подписью сверху — для панелей фильтров. */
export function Select<T extends string>({ label, value, onChange, options }: Props<T>) {
  return (
    <label className={styles.field}>
      <span className={styles.label}>{label}</span>
      <select
        value={value}
        onChange={(event) => {
          // Значение всегда одно из options: select не даёт ввести другое.
          const option = options.find((item) => item.value === event.target.value);
          if (option) onChange(option.value);
        }}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

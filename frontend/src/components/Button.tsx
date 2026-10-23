import type { ButtonHTMLAttributes } from "react";

import styles from "./Button.module.css";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "quiet" | "danger";
  busy?: boolean;
}

/** Кнопка; busy — действие выполняется: кнопка недоступна, текст не прыгает. */
export function Button({ variant = "secondary", busy = false, className, disabled, ...props }: Props) {
  return (
    <button
      type="button"
      {...props}
      className={[styles.button, styles[variant], className].filter(Boolean).join(" ")}
      disabled={disabled === true || busy}
      aria-busy={busy || undefined}
    />
  );
}

import { useMutation } from "@tanstack/react-query";
import { type SubmitEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { api, unwrap } from "../api/client";
import { tokens } from "../api/tokens";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { ApiError, errorText } from "../lib/errors";
import { useIsLoggedIn } from "../lib/useAuth";
import styles from "./LoginPage.module.css";

function redirectTarget(state: unknown): string {
  if (typeof state === "object" && state !== null && "from" in state) {
    const from = state.from;
    if (typeof from === "string" && from.startsWith("/") && from !== "/login") return from;
  }
  return "/";
}

export function LoginPage() {
  const loggedIn = useIsLoggedIn();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const target = redirectTarget(location.state);

  const login = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/login", { body: { email, password } })),
    onSuccess: (pair) => {
      tokens.save(pair);
      void navigate(target, { replace: true });
    },
  });

  if (loggedIn && !login.isPending) return <Navigate to={target} replace />;

  const onSubmit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    login.mutate();
  };

  const wrongCredentials = login.error instanceof ApiError && login.error.status === 401;
  return (
    <div className={styles.page}>
      <form className={styles.form} onSubmit={onSubmit}>
        <div className={styles.brand}>
          <Logo size={32} />
          <h1>JobRadar</h1>
        </div>
        <p className={styles.lead}>Вакансии с оценкой по вашему резюме.</p>

        <label className={styles.field}>
          Почта
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            aria-invalid={wrongCredentials || undefined}
          />
        </label>
        <label className={styles.field}>
          Пароль
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={wrongCredentials || undefined}
          />
        </label>

        {login.error && (
          <p className={styles.error} role="alert">
            {wrongCredentials ? "Неверная почта или пароль." : errorText(login.error)}
          </p>
        )}

        <Button type="submit" variant="primary" busy={login.isPending}>
          {login.isPending ? "Входим…" : "Войти"}
        </Button>
        <p className={styles.hint}>
          Пользователя создаёт команда <code>python -m app.cli create-user</code>.
        </p>
      </form>
    </div>
  );
}

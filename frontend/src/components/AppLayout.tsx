import { Link, NavLink, Outlet } from "react-router";

import { useMe } from "../api/hooks";
import { useLogout } from "../lib/useAuth";
import styles from "./AppLayout.module.css";
import { Button } from "./Button";
import { Logo } from "./Logo";

const NAV = [
  { to: "/", label: "Лента", end: true },
  { to: "/applications", label: "Отклики", end: false },
  { to: "/settings", label: "Настройки", end: false },
];

export function AppLayout() {
  const me = useMe();
  const logout = useLogout();
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.bar}>
          <Link to="/" className={styles.brand}>
            <Logo />
            JobRadar
          </Link>
          <nav className={styles.nav} aria-label="Разделы">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => (isActive ? `${styles.link} ${styles.active}` : styles.link)}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className={styles.user}>
            {me.data && <span className={styles.email}>{me.data.email}</span>}
            <Button variant="quiet" onClick={logout}>
              Выйти
            </Button>
          </div>
        </div>
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}

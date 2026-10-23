import { Navigate, Outlet, useLocation } from "react-router";

import { useIsLoggedIn } from "../lib/useAuth";

/** Без входа — на страницу входа; после входа вернёт туда, откуда пришли. */
export function RequireAuth() {
  const loggedIn = useIsLoggedIn();
  const location = useLocation();
  if (!loggedIn) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useSyncExternalStore } from "react";

import { tokens } from "../api/tokens";

/** Вошёл ли пользователь: меняется при входе, выходе и истёкшем refresh-токене. */
export function useIsLoggedIn(): boolean {
  return useSyncExternalStore(tokens.subscribe, tokens.isLoggedIn);
}

export function useLogout(): () => void {
  const client = useQueryClient();
  return useCallback(() => {
    tokens.clear();
    // Данные прошлого входа не должны мелькнуть после следующего.
    client.clear();
  }, [client]);
}

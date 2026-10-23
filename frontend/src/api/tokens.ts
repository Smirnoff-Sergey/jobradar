// Access-токен живёт 15 минут и хранится только в памяти; refresh — в localStorage,
// чтобы вход переживал перезагрузку страницы. Пользователь один, сервис личный.
const REFRESH_KEY = "jobradar.refresh";

type Listener = () => void;

let accessToken: string | null = null;
const listeners = new Set<Listener>();

function notify(): void {
  for (const listener of listeners) listener();
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export const tokens = {
  access: (): string | null => {
    return accessToken;
  },

  refresh: (): string | null => {
    return localStorage.getItem(REFRESH_KEY);
  },

  isLoggedIn: (): boolean => {
    return tokens.refresh() !== null;
  },

  save: (pair: TokenPair): void => {
    const wasLoggedIn = tokens.isLoggedIn();
    accessToken = pair.access_token;
    localStorage.setItem(REFRESH_KEY, pair.refresh_token);
    if (!wasLoggedIn) notify();
  },

  clear: (): void => {
    accessToken = null;
    localStorage.removeItem(REFRESH_KEY);
    notify();
  },

  subscribe: (listener: Listener): () => void => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

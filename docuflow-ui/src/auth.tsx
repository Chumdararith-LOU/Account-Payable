import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import api, { getToken, setToken, SIGNED_OUT_EVENT } from './api/client';

export interface User {
  username: string;
  display_name: string;
  role: 'admin' | 'reviewer';
  active: boolean;
  must_change_password: boolean;
}

interface LoginResponse {
  token: string;
  expires_in: number;
  user: User;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (current: string, next: string) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(() => getToken() !== null);

  // Resume a session saved in this browser.
  useEffect(() => {
    if (!getToken()) return;
    api
      .get<User>('/auth/me')
      .then((res) => setUser(res.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  // Any 401 (expired session, deactivated account) signs the browser out.
  useEffect(() => {
    const onSignedOut = () => {
      setUser(null);
      queryClient.clear();
    };
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut);
  }, [queryClient]);

  const start = useCallback(
    (res: LoginResponse) => {
      queryClient.clear();
      setToken(res.token);
      setUser(res.user);
    },
    [queryClient],
  );

  const login = useCallback(
    async (username: string, password: string) => {
      const res = await api.post<LoginResponse>('/auth/login', { username, password });
      start(res.data);
    },
    [start],
  );

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout');
    } catch {
      /* already signed out on the server */
    }
    setToken(null);
    setUser(null);
    queryClient.clear();
  }, [queryClient]);

  const changePassword = useCallback(
    async (current: string, next: string) => {
      const res = await api.post<LoginResponse>('/auth/password', { current_password: current, new_password: next });
      start(res.data);
    },
    [start],
  );

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, changePassword }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}

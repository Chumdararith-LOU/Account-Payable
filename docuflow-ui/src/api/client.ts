import axios from 'axios';

// People sign in (D-118): the session token lives in this browser and is sent
// as a Bearer header. There is no API key in the page any more.
// VITE_API_URL is only for development against another host; on the server
// the UI and the API share one origin and the API sits under /api.

const TOKEN_KEY = 'docuflow.session';
export const SIGNED_OUT_EVENT = 'docuflow:signed-out';

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode: the session lasts until the tab closes */
  }
}

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || '/api' });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const code = err?.response?.data?.error_code;
    if (err?.response?.status === 401 && (code === 'SESSION_INVALID' || code === 'AUTH_MISSING')) {
      setToken(null);
      window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
    }
    return Promise.reject(err);
  },
);

/** The API's message for a failed request, or a generic one. */
export function apiErrorText(err: unknown, fallback = 'The request failed. Is the server reachable?'): string {
  const e = err as { response?: { data?: { detail?: unknown } } };
  const detail = e?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

export default api;

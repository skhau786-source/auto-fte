import axios, { AxiosError } from "axios";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const api = axios.create({
  baseURL: API_URL,
  timeout: 15000,
});

export const TOKEN_KEY = "testing_frontend_token";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// Attach Bearer token to every request if one is stored.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export type ApiResult<T = unknown> = {
  ok: boolean;
  status?: number;
  ms: number;
  data?: T;
  error?: string;
};

function describeError(err: AxiosError): string {
  if (!err.response) {
    return `Network error — is the backend running at ${API_URL}? (${err.message})`;
  }
  const data = err.response.data as Record<string, unknown>;
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return `HTTP ${err.response.status}`;
}

/** Run an API call and return a normalized {ok, status, ms, data, error} result. */
export async function execute<T = unknown>(
  fn: () => Promise<{ status: number; data: T }>
): Promise<ApiResult<T>> {
  const t0 = performance.now();
  try {
    const res = await fn();
    return {
      ok: true,
      status: res.status,
      ms: Math.round(performance.now() - t0),
      data: res.data,
    };
  } catch (e) {
    const err = e as AxiosError;
    return {
      ok: false,
      status: err.response?.status,
      ms: Math.round(performance.now() - t0),
      data: err.response?.data as T | undefined,
      error: describeError(err),
    };
  }
}

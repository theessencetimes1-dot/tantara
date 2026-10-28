export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
const base = process.env.NEXT_PUBLIC_API_BASE_URL
  ? process.env.NEXT_PUBLIC_API_BASE_URL.replace(/\/$/, '') + '/api/v1'
  : '/api/v1';
export function authToken(): string | null {
  if (typeof document === 'undefined') return null;
  const c = document.cookie.split('; ').find((x) => x.startsWith('tantara_token='));
  return c?.slice('tantara_token='.length) ?? localStorage.getItem('tantara_token');
}
async function request<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  signal?.addEventListener('abort', () => controller.abort(), { once: true });
  try {
    const headers = new Headers(init.headers);
    if (!(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
    const bearer = authToken();
    if (bearer) headers.set('Authorization', `Bearer ${bearer}`);
    const response = await fetch(`${base}${path}`, { ...init, headers, signal: controller.signal });
    if (response.status === 401 && typeof window !== 'undefined' && window.location.pathname !== '/') {
      window.location.assign('/');
    }
    if (!response.ok) {
      let payload: { error?: { code?: string; message?: string; details?: unknown } } = {};
      try {
        payload = await response.json();
      } catch {
        /* response may be empty */
      }
      throw new ApiError(
        response.status,
        payload.error?.code ?? 'request_failed',
        payload.error?.message ?? response.statusText,
        payload.error?.details,
      );
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}
export const api = {
  get: <T>(p: string, signal?: AbortSignal) => request<T>(p, { method: 'GET' }, signal),
  post: <T>(p: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(
      p,
      { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body ?? {}) },
      signal,
    ),
  patch: <T>(p: string, body: unknown, signal?: AbortSignal) =>
    request<T>(p, { method: 'PATCH', body: JSON.stringify(body) }, signal),
  put: <T>(p: string, body: unknown, signal?: AbortSignal) =>
    request<T>(p, { method: 'PUT', body: JSON.stringify(body) }, signal),
  del: <T>(p: string) => request<T>(p, { method: 'DELETE' }),
};
export function persistToken(value: string) {
  localStorage.setItem('tantara_token', value);
  document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
}
export function clearToken() {
  localStorage.removeItem('tantara_token');
  document.cookie = 'tantara_token=; Path=/; Max-Age=0; SameSite=Lax';
}
export const apiBase = base;

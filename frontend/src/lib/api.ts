// In production VITE_API_URL is the EC2 backend origin (e.g. https://fintrack.duckdns.org).
// In dev it is unset, so paths stay relative and the Vite proxy handles them.
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? '';

// CSRF-exempt public endpoints — these never need the X-CSRF-Token header
const CSRF_EXEMPT = new Set([
  '/api/auth/login',
  '/api/auth/login/mfa',
  '/api/auth/register',
  '/api/auth/password-reset/request',
  '/api/auth/password-reset/confirm',
  '/api/auth/verify-email',
  '/api/auth/accept-invite',
]);

let _csrfToken: string | null = null;
let _onUnauth: (() => void) | null = null;

export function setCsrfToken(token: string | null) {
  _csrfToken = token;
}

export function setUnauthHandler(handler: () => void) {
  _onUnauth = handler;
}

async function refreshCsrfToken(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/auth/csrf`, { credentials: 'include' });
  if (!res.ok) return;
  const data = await res.json();
  _csrfToken = data.csrf_token as string;
}

// skipUnauth: true suppresses the session-expired callback (use on login/verify
// calls where a 401 is an expected wrong-credentials response, not expiry)
export async function api(
  path: string,
  options: RequestInit & { skipUnauth?: boolean } = {},
): Promise<Response> {
  const { skipUnauth = false, ...fetchOptions } = options;
  const method = (fetchOptions.method ?? 'GET').toUpperCase();
  const mutating = method === 'POST' || method === 'PATCH' || method === 'DELETE';

  const headers = new Headers(fetchOptions.headers);

  if (mutating && !CSRF_EXEMPT.has(path)) {
    if (!_csrfToken) {
      await refreshCsrfToken();
    }
    if (_csrfToken) {
      headers.set('X-CSRF-Token', _csrfToken);
    }
  }

  // FormData sets its own multipart Content-Type (with boundary) — never override it.
  if (!headers.has('Content-Type') && fetchOptions.body && !(fetchOptions.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(`${API_BASE}${path}`, { ...fetchOptions, headers, credentials: 'include' });

  if (res.status === 401 && !skipUnauth) {
    _csrfToken = null;
    _onUnauth?.();
  }

  return res;
}

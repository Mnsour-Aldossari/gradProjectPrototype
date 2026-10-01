const TOKEN_KEY = 'uav.token'
const LEGACY_USER_KEY = 'uav.user' // older versions stored a copy of the user here; it is never read any more

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

/** Returns false when storage is unavailable (private mode). */
function write(key: string, value: string | null): boolean {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
    return true
  } catch {
    return false
  }
}

// Only used when storage is unavailable: the session then lasts until reload.
let fallbackToken: string | null = null

/** The token is always read from storage, so clearing storage ends the session. */
export function getToken(): string | null {
  return read(TOKEN_KEY) ?? fallbackToken
}

export function saveSession(token: string): void {
  fallbackToken = write(TOKEN_KEY, token) ? null : token
  write(LEGACY_USER_KEY, null)
}

export function clearSession(): void {
  fallbackToken = null
  write(TOKEN_KEY, null)
  write(LEGACY_USER_KEY, null)
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

type Detail = string | { msg: string; loc?: (string | number)[] }[] | undefined

function describe(detail: Detail, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc?.slice(-1)[0] ?? 'input'}: ${d.msg}`).join('; ')
  return fallback
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(path, {
    method: options.method ?? 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  if (res.status === 401 && !path.endsWith('/login')) {
    clearSession()
    window.location.assign('/login')
  }
  if (!res.ok) {
    let detail: Detail
    try {
      detail = (await res.json()).detail
    } catch {
      detail = undefined
    }
    throw new ApiError(res.status, describe(detail, `Request failed (${res.status})`))
  }
  return (await res.json()) as T
}

export function liveUrl(missionId: number): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/ws/missions/${missionId}?token=${encodeURIComponent(getToken() ?? '')}`
}

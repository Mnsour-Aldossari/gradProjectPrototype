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

// One-shot flag so the login page can say why the user is there. It holds no path and no user data.
const EXPIRED_KEY = 'uav.sessionExpired'

function markSessionExpired(): void {
  try {
    sessionStorage.setItem(EXPIRED_KEY, '1')
  } catch {
    // The message is a courtesy; without storage the login page simply shows no message.
  }
}

export function peekSessionExpired(): boolean {
  try {
    return sessionStorage.getItem(EXPIRED_KEY) === '1'
  } catch {
    return false
  }
}

export function clearSessionExpired(): void {
  try {
    sessionStorage.removeItem(EXPIRED_KEY)
  } catch {
    // nothing to clear
  }
}

/**
 * The server no longer accepts our token: end the session and go to the login page with a message.
 * `hadSession` says whether the rejected request carried a token. It is not read from storage here,
 * because another open tab may already have cleared the shared token.
 */
export function endExpiredSession(hadSession: boolean): void {
  clearSession()
  if (hadSession) markSessionExpired()
  window.location.assign('/login')
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
  if (res.status === 401 && !path.endsWith('/login')) endExpiredSession(token !== null)
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

/** Fetches a file (with the session's token) and hands it to the browser to save as `filename`. */
export async function download(path: string, filename: string): Promise<void> {
  const token = getToken()
  const res = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (res.status === 401) endExpiredSession(token !== null)
  if (!res.ok) {
    let detail: Detail
    try {
      detail = (await res.json()).detail
    } catch {
      detail = undefined
    }
    throw new ApiError(res.status, describe(detail, `Download failed (${res.status})`))
  }
  const url = URL.createObjectURL(await res.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

/** The live link's address. The token is not in it: the page sends it as the first message once the socket is open,
 *  so it stays out of access logs, proxy logs and browser history. */
export function liveUrl(missionId: number): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/ws/missions/${missionId}`
}

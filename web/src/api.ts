import type { User } from './types'

const TOKEN_KEY = 'uav.token'
const USER_KEY = 'uav.user'

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // Storage unavailable (private mode): the session lasts until reload.
  }
}

let memoryToken: string | null = read(TOKEN_KEY)

export function getToken(): string | null {
  return memoryToken
}

export function getStoredUser(): User | null {
  const raw = read(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as User
  } catch {
    return null
  }
}

export function saveSession(token: string, user: User): void {
  memoryToken = token
  write(TOKEN_KEY, token)
  write(USER_KEY, JSON.stringify(user))
}

export function clearSession(): void {
  memoryToken = null
  write(TOKEN_KEY, null)
  write(USER_KEY, null)
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

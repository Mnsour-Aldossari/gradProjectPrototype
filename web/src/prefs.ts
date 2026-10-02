import { createContext, createElement, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useState, type ReactNode } from 'react'
import { useAuth } from './auth'

/**
 * Display preferences, kept per user on this device. They change how pages look, never what a user may see.
 * Storage can be unavailable (private mode); every read and write is guarded and falls back to the defaults.
 */
export type ThemePref = 'light' | 'dark' | 'system'

export interface Prefs {
  theme: ThemePref
}

export const DEFAULT_PREFS: Prefs = { theme: 'light' }

const THEMES: ThemePref[] = ['light', 'dark', 'system']

const userKey = (username: string) => `uav.prefs.v1.${username}`
// The preferences last applied on this device, read by the script in index.html before the first paint.
const LAST_KEY = 'uav.prefs.last'

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
    // Without storage the preferences last until the page is reloaded.
  }
}

/** Stored values are checked one by one, so an old or edited entry cannot break the page. */
function parse(raw: string | null): Prefs {
  let stored: Partial<Record<keyof Prefs, unknown>> = {}
  try {
    const value: unknown = raw ? JSON.parse(raw) : null
    if (value && typeof value === 'object') stored = value
  } catch {
    // unreadable entry: defaults
  }
  return {
    theme: THEMES.includes(stored.theme as ThemePref) ? (stored.theme as ThemePref) : DEFAULT_PREFS.theme,
  }
}

const darkQuery = () => window.matchMedia('(prefers-color-scheme: dark)')

function apply(prefs: Prefs): void {
  const root = document.documentElement
  root.dataset.theme = prefs.theme === 'system' ? (darkQuery().matches ? 'dark' : 'light') : prefs.theme
  write(LAST_KEY, JSON.stringify(prefs))
}

interface PrefsState {
  prefs: Prefs
  setPrefs: (change: Partial<Prefs>) => void
  reset: () => void
}

const PrefsContext = createContext<PrefsState | null>(null)

export function PrefsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const username = user?.username ?? null
  // Before sign-in (login page) the page keeps what this device showed last.
  const [prefs, setPrefsState] = useState<Prefs>(() => parse(read(LAST_KEY)))

  useEffect(() => {
    if (username) setPrefsState(parse(read(userKey(username))))
  }, [username])

  useLayoutEffect(() => {
    apply(prefs)
    if (prefs.theme !== 'system') return
    const query = darkQuery()
    const follow = () => apply(prefs)
    query.addEventListener('change', follow)
    return () => query.removeEventListener('change', follow)
  }, [prefs])

  const setPrefs = useCallback(
    (change: Partial<Prefs>) => {
      const next = { ...prefs, ...change }
      if (username) write(userKey(username), JSON.stringify(next))
      setPrefsState(next)
    },
    [prefs, username],
  )

  const reset = useCallback(() => {
    if (username) write(userKey(username), null)
    setPrefsState(DEFAULT_PREFS)
  }, [username])

  const value = useMemo(() => ({ prefs, setPrefs, reset }), [prefs, setPrefs, reset])
  return createElement(PrefsContext.Provider, { value }, children)
}

export function usePrefs(): PrefsState {
  const ctx = useContext(PrefsContext)
  if (!ctx) throw new Error('usePrefs must be used inside PrefsProvider')
  return ctx
}

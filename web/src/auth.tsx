import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api, clearSession, getToken, saveSession } from './api'
import type { User } from './types'

interface AuthState {
  user: User | null
  /** False until the stored token (if any) has been checked against the server. */
  ready: boolean
  login: (username: string, password: string) => Promise<User>
  logout: () => void
}

/** Where each role lands after signing in: field personnel get the mobile field view. */
export function homePath(user: User): string {
  return user.role === 'field_operator' ? '/field' : '/'
}

/** Pages that belong to one role only; every other page is open to both roles. */
export function canAccess(user: User, path: string): boolean {
  if (path === '/field' || path.startsWith('/field/')) return user.role === 'field_operator'
  if (path === '/missions/new') return user.role === 'supervisor'
  return true
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  // The token the current user was loaded for, to notice when storage changes underneath us.
  const loadedToken = useRef<string | null>(null)

  // The user (and so the role) always comes from the server for the current token, never from a stored copy.
  const loadUser = useCallback(() => {
    const token = getToken()
    loadedToken.current = token
    if (!token) {
      setUser(null)
      setReady(true)
      return
    }
    api<User>('/api/auth/me')
      .then((u) => {
        if (loadedToken.current === token) setUser(u)
      })
      .catch(() => {
        if (loadedToken.current === token) setUser(null)
      })
      .finally(() => setReady(true))
  }, [])

  useEffect(() => {
    loadUser()
    // Storage cleared or changed (other tab, dev tools): follow it as soon as the page is used again.
    const resync = () => {
      if (getToken() !== loadedToken.current) loadUser()
    }
    window.addEventListener('storage', resync)
    window.addEventListener('focus', resync)
    document.addEventListener('visibilitychange', resync)
    return () => {
      window.removeEventListener('storage', resync)
      window.removeEventListener('focus', resync)
      document.removeEventListener('visibilitychange', resync)
    }
  }, [loadUser])

  const login = useCallback(async (username: string, password: string) => {
    const res = await api<{ token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: { username, password },
    })
    saveSession(res.token)
    loadedToken.current = getToken()
    setUser(res.user)
    return res.user
  }, [])

  // A full page load drops all in-memory state; the page is left without re-rendering so no path is remembered.
  const logout = useCallback(() => {
    clearSession()
    window.location.assign('/login')
  }, [])

  const value = useMemo(() => ({ user, ready, login, logout }), [user, ready, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth()
  const location = useLocation()
  if (!ready) return null
  if (!user) return <Navigate to="/login" replace />
  // A page that belongs to the other role goes to this user's own home page.
  if (!canAccess(user, location.pathname)) return <Navigate to={homePath(user)} replace />
  return children
}

/** The desktop home (mission list) for supervisors; field personnel are sent to the field view. */
export function HomeRoute({ missions }: { missions: ReactNode }) {
  const { user } = useAuth()
  if (user?.role === 'field_operator') return <Navigate to="/field" replace />
  return missions
}

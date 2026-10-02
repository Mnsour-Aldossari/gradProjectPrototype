import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { clearSessionExpired, peekSessionExpired } from '../api'
import { homePath, useAuth } from '../auth'

export function LoginPage() {
  const { user, ready, login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Set when the server rejected the token; kept until the next successful sign-in.
  const [expired] = useState(peekSessionExpired)

  // Always land on the home page of the role that just signed in, never on a page remembered from before.
  if (!ready) return null
  if (user) return <Navigate to={homePath(user)} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const signedIn = await login(username.trim(), password)
      clearSessionExpired()
      navigate(homePath(signedIn), { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login">
      <div className="login-mark" aria-hidden="true">
        <svg viewBox="0 0 120 104">
          <path d="M60 6 L114 98 H6 Z" fill="none" stroke="currentColor" strokeWidth="6" strokeLinejoin="round" />
          <path d="M60 30 L88 80 H32 Z" className="login-mark-inner" />
        </svg>
      </div>
      <h1>UAV Landmine Survey</h1>
      <p className="lede">
        Mission planning, live UAV monitoring and adaptive classification of potential detections. Graduation project
        prototype, Prince Sattam Bin Abdulaziz University.
      </p>
      {expired && (
        <div className="notice" role="status">
          <p lang="ar" dir="rtl">
            انتهت الجلسة، سجّل دخولك من جديد
          </p>
          <p className="small">Your session has ended. Sign in again.</p>
        </div>
      )}
      <form className="login-form" onSubmit={submit}>
        <label className="field">
          <span>Username</span>
          <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="button" type="submit" disabled={busy}>
          {busy ? 'Signing in' : 'Sign in'}
        </button>
      </form>
      <p className="small">
        Demo accounts for the supervisor and the field operator are listed in <code>backend/app/seed.py</code>. All
        survey data in this prototype is simulated.
      </p>
    </main>
  )
}

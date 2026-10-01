import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const from = (location.state as { from?: string } | null)?.from ?? '/'
  if (user) return <Navigate to={from} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(username.trim(), password)
      navigate(from, { replace: true })
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
